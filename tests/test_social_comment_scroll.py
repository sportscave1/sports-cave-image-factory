"""No live accounts: viewport protocol, visible cards and mutation acknowledgements."""
import subprocess
from unittest.mock import Mock, patch

import pytest
from streamlit.testing.v1 import AppTest

from meta_social import CommunityError, MetaCommunity
from social_community_feed import merge_post
from social_comment_scroll import SCROLL_JS
from tests import test_meta_social as contracts
from tests.community_fixtures import FakeCommunity, READS, ADMIN


def test_viewport_observer_only_loads_once_until_the_user_scrolls_and_cleans_up():
    source = SCROLL_JS.replace("export default function", "const render = function", 1)
    harness = r'''
const assert = (await import('node:assert/strict')).default;
let callback, scroll, disconnected=0, removed=0, calls=[];
const main={scrollTop:0}, target={getBoundingClientRect:()=>({top:100})};
globalThis.window={scrollY:0,innerHeight:800};
globalThis.document={hidden:false,querySelector:()=>main,
 addEventListener:(name,fn)=>{scroll=fn},removeEventListener:()=>{removed++}};
globalThis.IntersectionObserver=class {constructor(fn){callback=fn}observe(){}disconnect(){disconnected++}};
const root={querySelector:()=>target};
const mount=(token,enabled=true)=>render({parentElement:root,data:{token,enabled},setTriggerValue:(...args)=>calls.push(args)});
let cleanup=mount('0'); callback([{isIntersecting:true}]); callback([{isIntersecting:true}]);
assert.deepEqual(calls,[['load','0']]); cleanup();
cleanup=mount('1'); callback([{isIntersecting:true}]); assert.equal(calls.length,1);
main.scrollTop=100; scroll(); assert.equal(calls.length,2); scroll(); assert.equal(calls.length,2);
cleanup(); cleanup=mount('2',false); main.scrollTop=200; scroll(); assert.equal(calls.length,2);
cleanup(); assert.equal(disconnected,3); assert.equal(removed,3);
'''
    result = subprocess.run(["node", "--input-type=module"], input=source + harness,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_merging_boosted_post_fills_blank_text_without_losing_ad_context_or_cursor():
    ad = {"id": "p", "ad_id": "a", "advertising": True,
          "comments": {"data": [{"id": "c", "text": ""}], "after": "ad-cursor", "comment_edge": "comments"}}
    organic = {"id": "p", "comments": {"data": [{"id": "c", "text": "Full comment", "username": "fan"}]}}
    merged = merge_post(ad, organic, "Instagram")
    assert merged["ad_id"] == "a"
    assert merged["comments"]["after"] == "ad-cursor"
    assert merged["comments"]["data"] == [{"id": "c", "text": "Full comment", "username": "fan"}]


@pytest.mark.parametrize("action", ["reply", "like", "delete", "hide", "unlike", "unhide"])
def test_unconfirmed_provider_mutation_does_not_report_success_or_retry(action):
    http = Mock()
    http.request.return_value = contracts.response({})
    api = MetaCommunity(dict(ADMIN), env=contracts.ENV, session=http)
    api.comments = Mock(return_value={"data": [{"id": "c"}], "after": ""})
    with pytest.raises(CommunityError, match="did not confirm"):
        api.moderate("Facebook", "p", "c", action, "Thanks")
    assert http.request.call_count == 1


def test_cards_are_visible_with_no_expanders_and_attachment_is_not_a_blank_comment():
    page = {"data": [{"id": "p", "comments": {"data": [{"id": "c", "attachment": {
        "media": {"image": {"src": "https://example.invalid/image.png"}}}}]}}], "after": ""}
    with patch.object(FakeCommunity, "comment_feed", return_value=page):
        app = AppTest.from_string(contracts.CommunityUiTests.SCRIPT).run()
        app.segmented_control[0].set_value("Comments").run()
    assert not app.exception
    assert not app.expander
    markup = "\n".join(item.value for item in app.markdown)
    assert 'loading="lazy"' in markup
    assert "[Comment]" not in markup
    assert len([b for b in app.button if str(b.key).startswith("comment-select-")]) == 2


def test_scroll_trigger_fetches_one_bounded_batch_and_editing_reuses_cached_reads():
    def pages(api, platform, after=""):
        READS.append(("posts", platform, after))
        if platform == "Instagram":
            return {"data": [], "after": ""}
        return {"data": [{"id": "p" + after, "comments": {"data": [{"id": "c" + after, "message": "Visible"}]}}],
                "after": "next" if not after else ""}
    READS.clear()
    with patch.object(FakeCommunity, "comment_feed", pages), patch("social_comment_scroll.scroll_request", side_effect=[True, False, False]):
        app = AppTest.from_string(contracts.CommunityUiTests.SCRIPT).run()
        app.segmented_control[0].set_value("Comments").run()
        assert app.session_state["community-comment-generation"] == 1
        assert len([b for b in app.button if str(b.key).startswith("comment-select-")]) == 2
        count = len(READS)
        app.button(key="comment-select-Facebook-c").click().run()
        assert len(READS) == count
        assert not app.exception

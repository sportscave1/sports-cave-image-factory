import unittest
import json
import shutil
import subprocess
from unittest.mock import patch, MagicMock
import app
import product_title_rules as titles
from tests.test_product_upload_prompts import ProductUploadFakeStreamlit, source_context


class ProductTitleTests(unittest.TestCase):
    def test_character_boundaries_count_spaces_punctuation_and_unicode(self):
        for count, level in ((0,"normal"),(35,"normal"),(55,"normal"),(56,"warning"),(60,"warning"),(61,"error")):
            value = titles.title_state("A" * count)
            self.assertEqual(value, {"count":count,"severity":level,"valid":count<=60})
        self.assertEqual(titles.title_state("José — NBA!")["count"], 11)

    def test_active_draft_live_and_existing_prompts_keep_the_rule_and_scope(self):
        for mode, existing in (("DRAFT",False),("LIVE",False),("DRAFT",True)):
            metadata={**source_context(), "customer_facing_title":"Michael Jordan — Legacy"}
            text=app.get_product_upload_prompt(metadata,update_existing=existing,publication_mode=mode)
            self.assertEqual(text.splitlines().count(titles.START),1)
            for marker in ("HARD MAXIMUM: 60", "35–55", "automatically rewrite", "not an estimated model count", "productCreate", "Wall Art only", "Existing products are not automatically renamed", "media-only updates preserve", "Michael Jordan — Legacy"):
                self.assertIn(marker,text)
            again=app.apply_product_upload_prompt_updates(text,metadata,update_existing=existing,publication_mode=mode)
            self.assertEqual(again,text)
            self.assertNotIn("Wall Art at the end",text)

    def test_non_preview_builder_rejects_oversize_candidate_without_truncation(self):
        candidate="Michael Jordan — " + "Long descriptive words "*4
        with self.assertRaisesRegex(ValueError,"exceeds 60"):
            app.get_product_upload_prompt({**source_context(),"customer_facing_title":candidate})
        self.assertEqual(candidate,"Michael Jordan — " + "Long descriptive words "*4)
        # A source identity isn't permission to rename an existing product.
        text=app.get_product_upload_prompt({**source_context(),"product_name":candidate},update_existing=True)
        self.assertIn("Existing products are not automatically renamed",text)

    def test_ui_blocks_prompt_handoff_and_clears_stale_submission_over_limit(self):
        fake=ProductUploadFakeStreamlit(upload_type=app.PRODUCT_UPLOAD_NEW_TYPE,product_name="Jordan",submitted=True)
        fake.session_state["product-upload-customer-title"]="A"*61
        fake.session_state["product-upload-submitted-prompt"]={"old":"prompt"}
        buttons=[]
        fake.button=lambda label,**kwargs: buttons.append(kwargs) or True
        with patch.object(app,"st",fake), patch.object(app,"current_product_upload_source_metadata",return_value=source_context()), patch.object(app,"log_app_memory"), patch.object(app,"get_components_module",return_value=MagicMock()), patch.object(app,"render_copyable_prompt") as render, patch.object(app,"record_product_upload_prompt_generation") as record:
            app.render_product_uploads_page()
        self.assertTrue(buttons[0]["disabled"])
        render.assert_not_called(); record.assert_not_called()
        self.assertNotIn("product-upload-submitted-prompt",fake.session_state)
        self.assertTrue(any("61 / 60" in x for x in fake.warnings))

    @unittest.skipUnless(shutil.which("node"), "Node required for live counter script check")
    def test_live_counter_updates_and_blocks_submit_per_keystroke(self):
        script = titles.LIVE_COUNTER_SCRIPT.removeprefix("<script>").removesuffix("</script>")
        harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
let counter;
const wrapper = {querySelector:()=>counter, appendChild:c=>counter=c};
const input = {value:'', closest:()=>wrapper, setAttribute:()=>{},
 addEventListener:(event,fn)=>input.listener=fn, removeEventListener:()=>{}};
const button={textContent:'Submit',disabled:false,dataset:{}};
const doc={querySelector:selector=>selector.startsWith("input")?input:counter,querySelectorAll:()=>[button],
 createElement:()=>({dataset:{},style:{},setAttribute:()=>{}})};
vm.runInNewContext(SCRIPT,{window:{parent:{document:doc}}});
for (const n of [0,55,56,60,61,60]) {
 input.value='A'.repeat(n); input.listener();
 assert.ok(counter.textContent.startsWith(`${n} / 60`));
 assert.equal(button.disabled,n>60);
 assert.equal(counter.style.color,n>60?'#c62828':n>55?'#996000':'inherit');
}
input.value='🏆 José'; input.listener(); assert.ok(counter.textContent.startsWith('6 / 60'));
""".replace("SCRIPT", json.dumps(script))
        result = subprocess.run([shutil.which("node"), "-e", harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ui_warning_title_can_generate_prompt(self):
        fake=ProductUploadFakeStreamlit(upload_type=app.PRODUCT_UPLOAD_NEW_TYPE,product_name="Jordan",submitted=True)
        fake.session_state["product-upload-customer-title"]="A"*60
        buttons=[]
        fake.button=lambda label,**kwargs: buttons.append(kwargs) or True
        with patch.object(app,"st",fake), patch.object(app,"current_product_upload_source_metadata",return_value=source_context()), patch.object(app,"current_os_user",return_value={}), patch.object(app,"log_app_memory"), patch.object(app,"get_components_module",return_value=MagicMock()), patch.object(app,"safe_startup_print"), patch.object(app,"render_copyable_prompt") as render, patch.object(app,"record_product_upload_prompt_generation"):
            app.render_product_uploads_page()
        self.assertFalse(buttons[0]["disabled"])
        self.assertTrue(any("60 / 60" in x for x in fake.warnings))
        self.assertIn("A"*60,render.call_args.args[1])

if __name__ == "__main__":
    unittest.main()

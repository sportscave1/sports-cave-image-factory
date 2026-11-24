"""Prepare only the existing OS duplicate's review asset; never publish a theme."""
import argparse
from pathlib import Path


def prepare(source):
    methods=(Path(__file__).resolve().parents[1]/'shopify/reviews/draft-review-methods.js').read_text(encoding='utf-8')
    body=methods.split('class DraftReviewMethods {',1)[1].rsplit('}',1)[0]
    start=min(source.index('  async nativeFeed('),source.index('  async nativePage('))
    end=source.index('  renderMedia() {',start)
    result=source[:start]+body+'\n'+source[end:]
    result=result.replace("first.full.includes('__1777871865832-ultimatemancavedecor__')", "review.id === '813945ea-267e-4f52-ab71-3a2c528ce98f' || first.full.includes('__1777871865832-ultimatemancavedecor__')")
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(prepare(args.source.read_text(encoding='utf-8')),encoding='utf-8')

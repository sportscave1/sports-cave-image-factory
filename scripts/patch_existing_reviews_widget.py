"""Prepare the narrowly scoped patch for the existing Shopify review widget.

Read the current theme first. Keep its original files outside Git for rollback.
This script only writes local files; it does not publish a theme.
"""
from pathlib import Path
import argparse

def patch(source, methods):
    if 'async nativeFeed()' in source:
        return source
    body=methods.split('class NativeReviewMethods {',1)[1].rsplit('}',1)[0]
    if '\n  });\n})();' in source:
        source=source.replace('\n  });\n})();',body+'\n  });\n})();')
        source=source.replace('const picture = review.media.find(item => !item.video);','const picture = review.media[0];')
        source=source.replace('      credit.append(verified);','      if (review.verified) credit.append(verified);')
    elif source.count('}})})();')==1:
        source=source.replace('}})})();','}'+body+'})})();')
        source=source.replace('const picture=review.media.find(item=>!item.video)','const picture=review.media[0]')
        source=source.replace('credit.append(verified),container.append(credit)','review.verified&&credit.append(verified),container.append(credit)')
    else:
        raise ValueError('The existing theme class changed; review it before patching.')
    return source

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    methods=Path(__file__).resolve().parents[1]/'shopify/reviews/native-review-methods.js'
    args.output.write_text(patch(args.source.read_text(encoding='utf-8'),methods.read_text(encoding='utf-8')),encoding='utf-8')

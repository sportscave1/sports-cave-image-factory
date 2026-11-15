"""Offline colour review CLI. Never connects to providers or overwrites artwork.

inspect --sources paths.json --output inspection.json (at most ten PSDs)
propose --request review-request.json --output proposal.json
approve --proposal proposal.json --reviewed-hash HASH --owner OWNER --output approved.json
template --source staged-template.psd --identity identity.json --policy approved.json --output new-template.psd
audit --catalogue checkpoint-snapshot.json --output colour-audit.json

member --source copy.psd --identity source.json --policy approved.json
       --provenance independent-evidence.json --verified-by OPERATOR --output member.json

A proposal request contains group, profile_path, members [{source,provenance}],
references/comparisons [{path,purpose}], and an optional explicit workflow scope.
No profile is guessed. Workflow defaults need owner approval, independently
verified membership receipts and explicit app/Companion configuration.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import auto_editions as ae
from auto_editions_colour_source import inspect_psd,stage_profile
from auto_editions_colour_policy import propose,approve,resolve,evidence_file,fingerprint


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as output:json.dump(value,output,indent=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    for name,options in dict(inspect=['sources'],propose=['request'],approve=['proposal','reviewed-hash','owner'],
                             template=['source','identity','policy'],audit=['catalogue'],
                             member=['source','identity','policy','provenance','verified-by']).items():
        command=sub.add_parser(name)
        for option in options:command.add_argument('--'+option,required=True)
        command.add_argument('--output',required=True)
    args=parser.parse_args()
    if Path(args.output).exists():raise ValueError('Use a new output; existing evidence is never overwritten.')
    if args.action=='inspect':
        paths=read(args.sources)
        if not isinstance(paths,list) or not 1<=len(paths)<=10:raise ValueError('Inspect one to ten representative PSDs.')
        rows=[]
        for path in paths:
            try:
                evidence=inspect_psd(path)
                rows.append(dict(name=Path(path).name,**{k:evidence[k] for k in ('state','profile','width','height','depth','mode')}))
            except (ValueError,OSError) as error:rows.append(dict(name=Path(path).name,state='inspector_failure',reason=str(error)))
        write(args.output,rows)
    elif args.action=='propose':
        request=read(args.request)
        evidence=lambda key:[evidence_file(e['path'],e['purpose']) for e in request[key]]
        proposal=propose(request['group'],Path(request['profile_path']).read_bytes(),request['members'],evidence('references'),evidence('comparisons'),scope=request.get('scope'))
        write(args.output,proposal)
        print('Review proposal fingerprint: '+fingerprint(proposal))
    elif args.action=='approve':
        write(args.output,approve(read(args.proposal),args.owner,args.reviewed_hash))
    elif args.action=='template':
        identity=read(args.identity)
        if ae.file_hash(args.source,dropbox=True)!=identity['content_hash']:raise ValueError('Template source identity changed.')
        icc,policy=resolve(identity,[read(args.policy)])
        proof=stage_profile(args.source,args.output,icc)
        write(args.output+'.proof.json',dict(policy=policy,integrity=proof,print_ready=False,
            acceptance='Reopen in Photoshop and verify layers, fonts, plaque, numbering, layout and embedded profile before publishing.'))
    elif args.action=='audit':
        from auto_editions_colour_recovery import audit
        write(args.output,audit(read(args.catalogue)))
    elif args.action=='member':
        from auto_editions_colour_workflows import verified_membership
        write(args.output,verified_membership(read(args.policy),args.source,read(args.identity),read(args.provenance),args.verified_by))


if __name__=='__main__':main()

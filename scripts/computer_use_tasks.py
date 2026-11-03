"""Local queue commands for a Codex session using the computer-use plugin.

This script handles only task data, never desktop input or helper startup.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    from app.computer_research import queue, claim, heartbeat, complete, ClaimRequest, LeaseRequest, CompleteRequest
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['list', 'claim', 'heartbeat', 'complete'])
    parser.add_argument('--job')
    parser.add_argument('--receipt', type=Path, help='Private local receipt file, containing claim response and ownership token')
    parser.add_argument('--result', type=Path, help='BrowserResult JSON file')
    args = parser.parse_args()
    if args.action == 'list':
        output = queue()
    elif args.action == 'claim':
        if not args.receipt:
            parser.error('领取任务时请通过 --receipt 指定私有回执文件')
        output = claim(ClaimRequest(job_id=args.job))
        if args.receipt and output.get('task'):
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(output, ensure_ascii=False), encoding='utf-8')
            output = {'task': output['task'], 'receipt': str(args.receipt.resolve()), 'expires_at': output['expires_at']}
        else:
            output = {k: v for k, v in output.items() if k != 'lease'}
            if output.get('task'):
                parser.error('领取任务时请通过 --receipt 指定私有回执文件')
    else:
        if not args.receipt:
            parser.error('需要 --receipt')
        receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
        job_id, lease = receipt['task']['job_id'], receipt['lease']
        if args.action == 'heartbeat':
            output = heartbeat(job_id, LeaseRequest(lease=lease))
        else:
            if not args.result:
                parser.error('需要 --result')
            output = complete(job_id, CompleteRequest(lease=lease, result=json.loads(args.result.read_text(encoding='utf-8'))))
    print(json.dumps(output, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()

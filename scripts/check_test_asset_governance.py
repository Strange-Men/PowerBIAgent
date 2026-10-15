"""Validate a repo-external governance receipt without inspecting artifact contents."""
import argparse
import json
from pathlib import Path


def validate(receipt):
    errors = []
    for field in ('sha_mismatch','active_old_path_reference','unclassified_db','unmigrated_known_synthetic_files'):
        if receipt.get(field) != 0: errors.append(field)
    if receipt.get('repository_touched') is not False: errors.append('repository_touched')
    if receipt.get('status') not in {'PASS','MANUAL_DELETE_REQUIRED','MANUAL_DELETE_COMPLETE'}: errors.append('status')
    if receipt.get('status') in {'PASS','MANUAL_DELETE_COMPLETE'} and receipt.get('old_test_directories') != 0:
        errors.append('old_test_directories')
    if receipt.get('status') == 'MANUAL_DELETE_COMPLETE':
        if receipt.get('repository_transient_directories') != 0:
            errors.append('repository_transient_directories')
        if receipt.get('manual_delete_paths'):
            errors.append('manual_delete_paths')
    if receipt.get('status') == 'MANUAL_DELETE_REQUIRED' and not receipt.get('manual_delete_paths'):
        errors.append('manual_delete_paths')
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receipt',type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
    errors = validate(receipt)
    if errors:
        print('Folder Governance FAIL: ' + ', '.join(errors))
        return 1
    print('Folder Governance ' + receipt['status'])
    return 0


if __name__ == '__main__': raise SystemExit(main())

"""Windowsの既存認証で選定モデルの設定・タグ定義を取得できるか確認する。"""
import json

from huggingface_hub import get_token, hf_hub_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError


def main():
    repo = 'animetimm/convnextv2_huge.dbv4-full'
    files = []
    try:
        for name in ('config.json', 'selected_tags.csv', 'preprocess.json'):
            path = hf_hub_download(repo, filename=name)
            files.append({'name': name, 'path': path})
    except GatedRepoError:
        print(json.dumps({'repo': repo, 'status': 'access_required', 'files': files,
                          'token_present': bool(get_token()),
                          'reason': 'モデル配布元での条件同意と、その権限を持つ認証が必要です。'}, ensure_ascii=False))
        return 2
    except HfHubHTTPError as error:
        print(json.dumps({'repo': repo, 'status': 'http_error',
                          'http_status': error.response.status_code if error.response is not None else None}))
        return 1
    print(json.dumps({'repo': repo, 'status': 'metadata_downloaded', 'files': files}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

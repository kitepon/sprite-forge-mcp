# p0-box — fox の ComfyUI 基盤

## 実施内容

- fox（Windows ネイティブ、RTX 5090）へ ComfyUI Portable の公式 Nvidia 配布を
  `C:\Users\kite_\ComfyUI` に展開した。実行環境は Python 3.13.14 と CUDA 13.0
  の PyTorch 2.13.0+cu130 で、ComfyUI は 0.34.0。
- `ComfyUI-RMBG` を `ComfyUI/custom_nodes/ComfyUI-RMBG` に導入し、portable Python
  環境へ同 node の requirements を導入した。
- NSSM の自動起動サービス `ComfyUI` を LocalSystem で登録した。起動コマンドは
  `main.py --listen 0.0.0.0 --port 8188`、作業ディレクトリは
  `C:\Users\kite_\ComfyUI` である。
- Windows Defender Firewall に受信規則 `ComfyUI TCP 8188`（TCP/8188）を追加した。
- `main-server` の ed25519 公開鍵を fox の
  `C:\Users\kite_\.ssh\authorized_keys` に登録した。

## 最終確認

2026-09-04 に次を実行して全て成功した。

1. fox: `Get-Service ComfyUI` が `Running`、`StartType` が `Automatic`。
2. fox: `GET http://127.0.0.1:8188/system_stats` が成功。
3. main-server: `curl --fail http://192.168.1.11:8188/system_stats` が成功し、
   `comfyui_version: 0.34.0` を返した。
4. main-server: `GET http://192.168.1.11:8188/object_info` の応答に `RMBG` と
   `toon` を確認した。

受入条件であるメインサーバーからの ComfyUI HTTP 到達性と RMBG node の可視性を満たす。

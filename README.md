# Local Video Mix Panel

本專案是一個本機影片音效合成工具，提供 CLI pipeline 和 Web 控制面板，用來分析主影片、切分參考音訊、建立時間軸，並輸出帶有混合音軌的影片。

This project is a local video audio-mixing tool with a CLI pipeline and a Web control panel. It analyzes a main video, slices reference audio, builds a timeline, and renders a final video with mixed audio layers.

## 日本語説明 / Japanese Overview

このプロジェクトは、ローカル環境で動画に効果音や参照音声を合成するためのツールです。CLI パイプラインと Web コントロールパネルを備えており、メイン動画の解析、参照音声の切り出し、タイムライン生成、音声ミックス付き動画の書き出しを行えます。

公開版には個人用の動画、音声素材、出力済みファイル、一時解析ファイル、ローカル設定ファイルは含まれていません。利用する場合は、自分のメディアファイルを `input/` に配置し、`config.example.ini` をコピーして `config.ini` を作成してください。

基本的な流れ：

1. `pip install -r requirements.txt` で依存パッケージをインストールします。
2. `copy config.example.ini config.ini` で設定ファイルを作成します。
3. `input/` フォルダーに動画と音声素材を入れます。
4. `python scripts/panel_app.py` を実行し、`http://127.0.0.1:5010` を開きます。
5. バッチ処理を使う場合は、`auto_schedule.example.txt` を `auto_schedule.txt` にコピーし、出力サフィックスと動画ファイル名だけを編集します。

## Public Package Notice / 公開版說明

公開版不包含任何個人素材、輸入影片、輸出影片、暫存分析檔、build 產物或本機 `config.ini`。

The public package does not include personal media, input videos, rendered videos, temporary analysis files, build artifacts, or a local `config.ini`.

請自行把媒體檔放到 `input/`，並從 `config.example.ini` 建立自己的 `config.ini`。

Place your own media files under `input/`, then create your own `config.ini` from `config.example.ini`.

## Features / 功能

- Web 面板：編輯設定、執行 pipeline、查看偵測摘要、預覽縮圖和音訊波形。
- Web panel: edit settings, run the pipeline, inspect detection summaries, preview frames and waveforms.
- 批次排程：用 profiles 依序輸出多個版本。
- Scheduled batch rendering: use profiles to render multiple outputs in order.
- 自動排程清單：只填影片檔名和輸出後綴即可產生排程。
- Simple schedule list: provide video names and one output suffix to generate a batch schedule.
- 防覆蓋保護：輸出檔已存在時會停止，避免誤覆蓋。
- Overwrite protection: rendering stops when an output file already exists.

## Requirements / 需求

- Windows 10/11
- Python 3.10 or newer
- FFmpeg available in `PATH`

安裝 Python 套件：

Install Python packages:

```bash
pip install -r requirements.txt
```

## Setup / 設定

1. 複製範例設定：

   Copy the example config:

   ```powershell
   copy config.example.ini config.ini
   ```

2. 放入媒體檔：

   Add your media files:

   ```text
   input/main.mp4
   input/ref.mp4
   input/shutter/shutter.m4a
   input/voice1/voice1.mp3
   input/voice2/voice2.mp3
   input/sfx/sfx.mp3
   input/mechanical/mechanical.mp3
   ```

3. 依需要編輯 `config.ini`。

   Edit `config.ini` as needed.

## Web Panel / Web 面板

啟動 Web 面板：

Start the Web panel:

```bash
python scripts/panel_app.py
```

然後開啟：

Then open:

```text
http://127.0.0.1:5010
```

Windows 也可以雙擊：

On Windows, you can also double-click:

```text
開啟使用者面板.bat
```

## CLI Usage / 命令列使用

單一輸出：

Single output:

```bash
python scripts/run_pipeline.py --ini config.ini
```

使用 `config.ini` 裡的 `[schedule] profiles`：

Use `[schedule] profiles` from `config.ini`:

```bash
python scripts/run_pipeline.py --ini config.ini --use-schedule
```

指定 profiles：

Run selected profiles:

```bash
python scripts/run_pipeline.py --ini config.ini --profiles main1,main2
```

## Simple Auto Schedule / 簡易自動排程

複製範例清單：

Copy the example list:

```powershell
copy auto_schedule.example.txt auto_schedule.txt
```

只改這兩種內容：

Edit only these two things:

```text
輸出後綴=_final

sample-main
sample-second-video.mp4
```

執行：

Run:

```bash
python scripts/auto_schedule.py auto_schedule.txt
```

Windows 可雙擊：

On Windows, double-click:

```text
自動排程輸出.bat
```

## Public Packaging / 公開版打包

建立乾淨公開包：

Create a clean public package:

```bash
python scripts/package_public.py
```

輸出位置：

Output:

```text
dist/local-video-mix-panel/
dist/local-video-mix-panel-public.zip
```

公開包只包含原始碼、範例設定、雙語說明和啟動腳本。

The public package includes only source code, example configs, bilingual documentation, and launcher scripts.

## Privacy Checklist / 去個人化檢查表

- 不提交 `input/`、`output/`、`work/`、`build/`。
- Do not commit `input/`, `output/`, `work/`, or `build/`.
- 不提交 `config.ini` 或 `auto_schedule.txt`。
- Do not commit `config.ini` or `auto_schedule.txt`.
- 不提交 `.mp4`、`.mp3`、`.wav`、`.m4a` 等媒體檔。
- Do not commit media files such as `.mp4`, `.mp3`, `.wav`, or `.m4a`.
- 發佈前執行 `python scripts/package_public.py`，只公開 `dist/local-video-mix-panel`。
- Before publishing, run `python scripts/package_public.py` and publish only `dist/local-video-mix-panel`.

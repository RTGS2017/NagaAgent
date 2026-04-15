<div align="center">

# NagaAgent

**アニメ超能力AIアシスタント**

ストリーミングツールコール · ナレッジグラフメモリ · Live2Dアバター · 音声インタラクション · Nagaネットワークコミュニティ

Nagaプロトコルは、チャット、メモリ、MCP、スキル、OpenClaw連携を統合し、クライアントサイドのアニメ超能力AIアシスタントを中心とした、実用的なAIツール群を構築します。

本ソフトウェアの機能: 1) ワンクリックログインですべてのAPIキーを自動設定し、Live2Dアバターを通じてNagaと自然に会話・チャットが可能; 2) 内蔵のOpenClawにより、関心のあるトピックの迅速な探索や、タスク指示リストからの完全自動実行が可能; 3) 会話履歴から3Dメモリの海を自動構築し、想起されたメモリを後続のチャットに注入; 4) 会話に残された手がかりの断片を通じて、Nagaネットワーク内の神秘的なNagaの世界を発見; 5) インタラクションや自動画面認識を通じて状況を理解し提案を行うゲームガイド機能を内蔵、MAAなどの自動化プラグインにも対応; 6) セルフ設定、ブラウザ制御、MusicBoxなど豊富な追加コンポーネントを搭載。

Nagaの未来は、あなた自身で切り拓いてください。

[简体中文](README.md) | [English](README_en.md) | [日本語](README_ja.md)

![NagaAgent](https://img.shields.io/badge/NagaAgent-5.1.0-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-AGPL%203.0%20%7C%20Proprietary-yellow?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)

[![Stars](https://img.shields.io/github/stars/Xxiii8322766509/NagaAgent?style=social)](https://github.com/Xxiii8322766509/NagaAgent)
[![Forks](https://img.shields.io/github/forks/Xxiii8322766509/NagaAgent?style=social)](https://github.com/Xxiii8322766509/NagaAgent)
[![Issues](https://img.shields.io/github/issues/Xxiii8322766509/NagaAgent)](https://github.com/Xxiii8322766509/NagaAgent/issues)

**[QQ Bot連携: Undefined QQbot](https://github.com/69gg/Undefined/)**

</div>

---

**デュアルライセンス** · オープンソース: [AGPL-3.0](LICENSE) · クローズドソース: [プロプライエタリライセンス](LICENSE-CLOSED-SOURCE)（書面による同意が必要）。
商用に関するお問い合わせ: contact@nagaagent.com / bilibili [柏斯阔落]

---

## 更新履歴

| 日付 | バージョン | 変更内容 |
|------|---------|---------|
| 🔧 2026-04-15 | — | 設定同期リファクタリング：source config と runtime config の双方向マージ；ASRヘルスチェックURLが設定値を使用；サービスポート取得と設定パスの再構築 |
| 🤖 2026-04-14 | — | Anthropic APIフォーマットサポートを追加（`api_format`フィールド）；五つ組抽出器がAnthropic SDKに対応；Live2D空テキスト呼び出しの処理 |
| 🐛 2026-04-12 | — | py2neo `Graph()` timeoutパラメータの非互換とNeo4j接続状態の誤検知を修正 |
| 🌐 2026-04-05 | — | フォーラム機能強化：フィードモードとアンロック進捗機能 |
| 📖 2026-03-21 | — | 日本語README（README_ja.md）を追加 |
| 🧳 2026-03-20 | — | 旅行モジュールワークフローとHubインストールフローの改善 |
| 📨 2026-03-17 | — | QQ通知：専用検証エンドポイント、サーバー側メンション処理、エラー伝播 |
| 🛠️ 2026-03-16 | — | フォーラム読み込みとパッケージビューの復元修正；macOS DMG署名とファイルシステム修正；OpenClawパッケージのソースからのコンパイルとランタイム修正 |
| 📦 2026-03-15 | — | OpenClawパッケージ版ランタイムの強化；テレメトリ通知とランタイム統合の改善；Windowsビルドスクリプトのコンソールエンコーディング修正 |
| 🛰️ 2026-03-14 | — | エージェントディレクトリがフル設定ダイアログにアップグレード（名前/ペルソナ/エンジン/SOUL.md/プライベートMCP & スキル）；スキルワークショップがNagaHubと一般的なMCPウォームアップに対応；旅行/探索フローにQQとFeishu完了コールバックを追加；クラウドメモリがローカルNeo4jへのフォールバックを廃止 |
| 🧩 2026-03-13 | — | OpenClawオーケストレーションとパッケージング統合をさらに拡張；バックエンド仕様でWindowsコンソールのUnicode出力エラーを修正 |
| 🧱 2026-03-11 | — | OpenClawスキル自動実行；エージェントごとの分離ワークスペース；モデルセレクターと価格表示がDefault / Deepseek-V3.2 / Kimi-K2.5に対応 |
| 🛠️ 2026-03-09 | — | OpenClawベンダーソースのディープコンパイルと統一設定フロー；ログアウトユーザー向けフォーラム401エラーの嵐を修正；Windowsトレイアイコン修復 |
| 📦 2026-03-08 | — | `naga-backend.spec`の修正を継続；アプリスキャナーが環境変数パスとmacOSに対応；ツール結果がデフォルトで折りたたみ表示；Ark Marketからメモリ移行/MCPツール/エージェントスキルセクションを削除 |
| 🚦 2026-03-07 | — | Node.jsとuvランタイムをアプリにバンドル；統一MCPコマンドリゾルバ；OpenClaw Gatewayの起動診断を強化；パッケージモードでの音楽・ウェイクボイス・Mind Seaの修正 |
| 🧰 2026-03-06 | — | GitHub Actionsビルド＆リリースパイプライン；Electron自動更新が旧パッチシステムを置換；CIリソースとcharset_normalizerのパッケージング修正；フォーラムとクレジットポーリングの改善 |
| 🔊 2026-03-05 | — | TTSトグル、メッセージキュー、シリアライズ送信フローのリファクタリング；RAGメモリ想起の強化；GeminiおよびFunction Calling自動サポート；チャージUIとリモートメモリの安定性修正 |
| 🧠 2026-03-04 | — | ネイティブFunction Callingに移行；DogTagがハートビート/プロアクティブビジョンを担当；フロントエンド・バックエンドのホットパッチシステム（4層安全機構）；よりスムーズなストリーミングテキストとプログレッシブTTS |
| 🔎 2026-03-03 | — | `web_search`がNagaBusiness検索プロキシに直接接続；フォーラム接続、ストリーミングTTS、OpenClawポーリングフォールバックの修正；Live2DとElectronの安定性修正 |
| ❤️ 2026-03-02 | — | ハートビートv3イベント駆動リファクタリング；`naga_control`自己オーケストレーションツール；`agent-browser`をパッケージビルドにバンドル；起動診断、ヘルスチェック、OpenClaw設定パスの修正 |
| 🌐 2026-03-01 | — | 検索プロキシフロー確定：ログイン時NagaBusiness、ログアウト時Brave / OpenClaw；OpenClawダイレクトツールコールと自動起動の改善；ゲームガイドと音声設定の更新 |
| 🗂️ 2026-02-28 | — | 永続ストレージを`~/.naga`に統一；ForumQuotaViewネットワーク探索コントロールセンター；旅行モジュールと音声インタラクションのアップグレード |
| 🎙️ 2026-02-27 | — | ASR音声認識統合（MediaRecorder + NagaBusinessプロキシ）；会話スタイル、Electron背景、MCPビジョン、サーバー設定のクリーンアップ |
| 🎆 2026-02-26 | 5.1.0 | Nagaネットワークコミュニティフォーラム公開；統一設定ページ（3-in-1リデザイン）；旅行モード；クレジットクォータページ；マーケット＆パネル更新 |
| ⚡ 2026-02-25 | 5.1.0 | TTSフルスタック修正（CORS / asyncio）；クロスプラットフォームbuild.py；コンテキスト圧縮の永続化；キャラクターシステム更新；プロンプトインジェクション対策リファクタリング |
| 🎵 2026-02-24 | — | Neo4j接続タイムアウト修正；統一BGMプレーヤー；MusicBoxプレイリストエディター；MCP管理UI；フローティングボール透過ウィンドウ＋ホバー明度アップ |
| 🏗️ 2026-02-23 | — | クロスプラットフォームビルド改善；pyproject.tomlでバージョン統一；プロンプト/スクリーンショット/ビジュアル最適化；キャラクターファイル移行＆パッケージング |
| 💕 2026-02-22 | — | クレジット＆好感度システム（チェックイン/好感度/クレジット）；フローティングボールの影＆ドラッグ修正；自動ログイン復元；OpenClawフック修正 |
| 🎶 2026-02-21 | — | MusicBoxアイコン更新；MCPエージェント更新；フローティングボールミニボタン |
| 🗜️ 2026-02-20 | — | 3層コンテキスト圧縮リファクタリング（`<compress>`タグ/クロスセッション継承）；MCP管理UI；フローティングボール透過ウィンドウ；MusicBox修正 |
| 🔄 2026-02-19 | — | SSEからbase64を除去、JSON直接ストリーミング；冗長なバックグラウンドインテント分析器を削除；config_managerのエンコーディング自動検出 |
| 🔧 2026-02-17 | — | フローティングボールのスプライトフレームパスを相対パスに変更、パッケージビルドでのアバター欠落を修正 |
| 🚀 2026-02-16 | 5.0.0 | NagaModelゲートウェイ統一アクセス；DeepSeek推論チェーンのリアルタイム表示；Mind Sea UIアダプティブ修正 |
| 🧠 2026-02-15 | — | 統一ナレッジブロック注入＋履歴汚染修正；LLMストリーミングリトライ；7日間自動ログイン；起動時自動開始 |
| 🌊 2026-02-14 | — | NagaMemoryクラウドリモートメモリ；Mind Sea 3Dリライト；スプラッシュパーティクルアニメーション；バージョン更新ダイアログ；利用規約 |
| ✨ 2026-02-13 | — | フローティングボール4状態モード；スクリーンショットマルチモーダルビジョン切替；スキルワークショップリファクタリング；Live2D感情チャンネル独立化 |
| 🎨 2026-02-12 | — | NagaCAS認証；Live2D 4チャンネル直交アニメーション；Agentic Tool Loop；アークナイツ風スプラッシュスクリーン |
| 📦 2026-02-11 | — | OpenClaw組み込みパッケージング；起動時にテンプレートから設定を自動生成 |
| 🛠️ 2026-02-10 | — | バックエンドパッケージング最適化；スキルワークショップMCPステータス修正；冗長なAgent/MCPを削除しOpenClawのみ保持 |
| 🌱 2026-02-09 | — | フロントエンドリファクタリング；Live2D視線追従無効化；OpenClawをAgentServerに改名 |

---

## 目次

1. [クイックスタート](#クイックスタート)
2. [機能概要（メインパネル）](#機能概要メインパネル)
3. [チャット](#1-チャット--messageview)
4. [Mind Sea](#2-mind-sea--mindview)
5. [スキルワークショップ](#3-スキルワークショップ--skillview)
6. [Nagaネットワーク](#4-nagaネットワーク--コミュニティフォーラム)
7. [Arkマーケット](#5-arkマーケット--marketview)
8. [ターミナル設定](#6-ターミナル設定--configview)
9. [MusicBox](#7-musicbox--musicview)
10. [フローティングボール](#8-フローティングボール--floatingview)
11. [グローバル機能](#グローバル機能)
12. [バックエンドアーキテクチャ](#バックエンドアーキテクチャ)
13. [オプション設定](#オプション設定)
14. [ポート](#ポート)
15. [トラブルシューティング](#トラブルシューティング)

---

## クイックスタート

### 必要環境

- Python 3.11（`>=3.11, <3.12`）
- オプション: [uv](https://github.com/astral-sh/uv) — より高速な依存関係インストール
- オプション: Neo4j — ローカルナレッジグラフメモリ

### インストール

```bash
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# フロントエンド
cd frontend
npm install
cd ..

# バックエンド
# 方法1: uv（推奨）
uv sync

# 方法2: 手動
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### 最小設定

`config.json.example`を`config.json`にコピーし、LLM APIの認証情報を入力してください：

```json
{
  "api": {
    "api_key": "your-api-key",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v3.2",
    "api_format": "openai"
  }
}
```

OpenAI互換の任意のAPI（DeepSeek、Qwen、OpenAI、Ollamaなど）で動作します。Anthropicネイティブフォーマットにも対応（`api_format`を`"anthropic"`に設定）。

### 起動

```bash
cd frontend && npm run dev   # ワンクリック起動（設定済み）
```

---

## 機能概要（メインパネル）

起動後、**メインパネル（PanelView）** に入ります。マウスの動きに連動した3Dパララックス効果（パースペクティブ回転）があります。
すべての機能はメインパネルの8つのエントリーボタンからアクセスできます：

| # | エントリー | ルート | 概要 |
|---|-------|-------|---------|
| 1 | **チャット** | `/chat` | AI会話、ストリーミングツールコール、コンテキスト圧縮 |
| 2 | **Mind Sea** | `/mind` | ナレッジグラフ3D可視化 & GRAGメモリ管理 |
| 3 | **スキルワークショップ** | `/skill` | MCPツール管理 & コミュニティスキルインストール |
| 4 | **Nagaネットワーク** | `/forum` / `/forum/quota` | コミュニティフォーラム、クレジット & 好感度 |
| 5 | **Arkマーケット** | `/market` | 背景、音楽、キャラクター、メモリ移行、チャージ |
| 6 | **ターミナル設定** | `/config` | モデル、メモリ & 音声/ビジュアル設定（3-in-1） |
| 7 | **MusicBox** | `/music` | BGMプレーヤー & プレイリスト管理 |
| 8 | **フローティングボール** | — | 軽量フローティングボールウィンドウモードに入る |

---

## 1. チャット · MessageView

### ストリーミングツールコール

チャットエンジンはSSE経由で出力をストリーミングし、フロントエンド表示とTTS文分割に同時送信します。
ツールコールはOpenAIのFunction Calling APIに依存せず、LLMが` ```tool``` `コードブロック内にJSONを埋め込むため、**OpenAI互換の任意のプロバイダーでそのまま動作します**。
`api_format: "anthropic"`でAnthropicネイティブAPIフォーマットにも対応。

**シングルラウンドツールコールフロー：**

```
LLMストリーミング出力 ──SSE──▶ フロントエンドリアルタイム表示
       │
       ▼
parse_tool_calls_from_text()
  ├─ フェーズ1: ```tool```コードブロックを抽出
  └─ フェーズ2: 裸のJSON抽出にフォールバック
       │
       ▼
  agentTypeでルーティング
  ├─ "mcp"      → MCPManager.unified_call()
  ├─ "openclaw" → Agent Server /openclaw/send
  └─ "live2d"   → UIアニメーション通知
       │
       ▼
  asyncio.gather() 全ツール並列実行
       │
       ▼
  結果をメッセージに注入、次のLLMラウンドを開始（最大5回）
```

- テキストパース: `json5`による寛容なパース、全角文字を自動正規化
- SSEフォーマット: `data: {"type":"content"|"reasoning","text":"..."}\n\n`（直接JSON、base64なし）
- ループ上限: `max_loop_stream = 5`（設定可能）

ソース: [`apiserver/agentic_tool_loop.py`](apiserver/agentic_tool_loop.py)

### コンテキスト圧縮

セッショントークンが10万を超えると自動的にトリガーされ、コンテキストのオーバーフローを防止します：

| フェーズ | トリガー | 動作 |
|-------|---------|---------|
| **起動時圧縮** | セッション読み込み | 履歴がしきい値を超えている場合、初期メッセージを即座に圧縮 |
| **ランタイム圧縮** | 各ラウンド後 | 上限超過時に圧縮し`<compress>`タグを注入 |
| **クロスセッション継承** | 新セッション開始 | 前回のサマリーを読み込み、蓄積されたコンテキストをロールアップ |

サマリー構造（6セクション）：重要な事実 / ユーザーの好み / 重要な決定 / TODO / 背景情報 / 最近の状態。
`<compress>`タグはセッションファイルに永続化されますが、LLMトークン統計にはカウントされません。

### DeepSeek推論チェーン表示

DeepSeek使用時、`reasoning`フィールドがSSE経由でリアルタイムにプッシュされ、フロントエンドで独自のスタイルで表示されます。

---

## 2. Mind Sea · MindView

### GRAGナレッジグラフメモリ

GRAG（Graph-RAG）は会話から五つ組を自動抽出し、Neo4jに保存して、関連するメモリをLLMコンテキストとして取得します。

**五つ組構造：** `(主語, 主語タイプ, 述語, 目的語, 目的語タイプ)`

**抽出パイプライン：**

1. 構造化抽出（推奨）: `beta.chat.completions.parse()` + Pydantic `QuintupleResponse`、`temperature=0.3`、最大3回リトライ
2. JSONフォールバック: パース失敗時、最初の`[`から最後の`]`までのコンテンツを抽出
3. フィルタリング: 事実（行動、関係、状態、好み）のみを保持；比喩、仮定、感情をフィルタリング

**エンティティタイプ：** `person` / `location` / `organization` / `item` / `concept` / `time` / `event` / `activity`

**タスクマネージャー：**
- 3つのasyncioワーカーが`asyncio.Queue(maxsize=100)`を消費
- SHA-256重複排除：同一の保留/実行中タスクはスキップ
- 1時間ごとに24時間以上経過したタスクをクリーンアップ

**デュアルストレージ：**
- ローカル: `logs/knowledge_graph/quintuples.json`
- クラウド: Neo4jグラフデータベース、`graph.merge()` upsert

**RAG検索：** キーワード抽出 → Cypherクエリ → `主語(タイプ) —[述語]→ 目的語(タイプ)` 形式でコンテキストに注入

**リモートメモリ：** ログインユーザーはNagaMemoryクラウドを優先利用；未ログイン時はローカルGRAGが利用可能。パフォーマンスコストを避けるため、クラウドパスはローカルNeo4jへの自動フォールバックを行わなくなりました。

ソース: [`summer_memory/`](summer_memory/)

### Mind Sea 3D可視化

Canvas 2D + 手動3D投影（WebGLではない）、球面座標カメラ、透視除算 `700 / depth`。

**7層レンダリング順序：**
背景グラデーション → 床グリッド → 水面 → ボリュメトリックライト（3本のゴッドレイ）→ パーティクルシステム（3層、125パーティクル）→ 生物発光プランクトン（10個、軌跡付き）→ ナレッジグラフノード & エッジ（深度ソート）

**グラフマッピング：** `subject/object` → ノード、`predicate` → 有向エッジ、次数中心性 → ノード高さの重み、100ノード制限

**インタラクション：** ドラッグで軌道回転、中クリックでパン、スクロールでズーム、ノードクリック/ドラッグ、キーワード検索フィルター

---

## 3. スキルワークショップ · SkillView

### 内蔵MCPエージェント

[Model Context Protocol](https://modelcontextprotocol.io/)に基づくプラグイン可能なツールアーキテクチャで、各ツールが独立したエージェントとして動作します：

| エージェント | 機能 |
|-------|----------|
| `weather_time` | 天気クエリ/予報、システム時刻、都市/IP自動検出 |
| `open_launcher` | インストール済みアプリのスキャン、自然言語でプログラム起動 |
| `game_guide` | ゲーム攻略Q&A、ダメージ計算、編成構築、自動スクリーンショット注入 |
| `online_search` | SearXNG経由のWeb検索 |
| `crawl4ai` | Crawl4AI経由のWebコンテンツ抽出 |
| `playwright_master` | Playwright経由のブラウザ自動化 |
| `vision` | スクリーンショット分析 & ビジュアルQ&A |
| `mqtt_tool` | MQTT経由のIoTデバイス制御 |
| `office_doc` | docx / xlsxコンテンツ抽出 |

**登録 & ディスカバリ：** `mcp_registry.py`が`**/agent-manifest.json`をglobスキャンし、`importlib.import_module`で動的にインスタンス化。

### MCP管理UI

フロントエンドの`McpAddDialog.vue`がグラフィカルなMCPツール管理インターフェースを提供 — 再起動不要でツールの追加・削除が可能。

### コミュニティスキルインストール

スキルワークショップはコミュニティ公開スキルのワンクリックインストールに対応（Agent Browser、Brainstorming、Context7、Firecrawl Searchなど）。
バックエンドエンドポイント: `GET /openclaw/market/items`、`POST /openclaw/market/items/{id}/install`

ソース: [`mcpserver/`](mcpserver/)

---

## 4. Nagaネットワーク · コミュニティフォーラム

### コミュニティフォーラム

メインパネルの「Nagaネットワーク」ブロックからアクセス可能な、完全埋め込み型コミュニティ：

| ビュー | ルート | 機能 |
|------|-------|----------|
| `ForumListView` | `/forum` | 投稿一覧、カテゴリフィルター |
| `ForumPostView` | `/forum/post/:id` | 投稿詳細 & 返信 |
| `ForumMessagesView` | `/forum/messages` | ダイレクトメッセージ |
| `ForumMyPostsView` | `/forum/my-posts` | 自分の投稿 |
| `ForumMyRepliesView` | `/forum/my-replies` | 自分の返信 |
| `ForumQuotaView` | `/forum/quota` | クレジットクォータ & 探索エントリー |

ソース: [`frontend/src/forum/`](frontend/src/forum/)

### クレジット & 好感度システム

ログインユーザー限定のゲーミフィケーションインタラクションシステム：

| 項目 | 説明 |
|-----------|-------------|
| **クレジット** | デイリーチェックインと連続ログインボーナスで獲得；モデルクォータの引き換えに使用 |
| **好感度** | チェックインごとに増加；Nagaとの関係の深さを反映 |
| **デイリーチェックイン** | ユーザーメニューからワンクリックチェックイン；連続チェックインでボーナス報酬が発動 |

関連API（APIサーバー経由でNagaポータルにプロキシ）: `/api/checkin`、`/api/affinity`、`/api/credits`

---

## 5. Arkマーケット · MarketView

Arkマーケットはすべてのリソース取得と管理を集約し、7つのタブに整理されています：

| タブ | 説明 |
|-----|-------------|
| **テーマ背景** | アプリケーションの背景テーマを切り替え |
| **ミュージックアレイ** | 音楽アルバムの購入/アンロック（現在: 砂の本） |
| **キャラクター登録** | AIキャラクターのバインド/切替（ログイン必須） |
| **メモリ移行** | クラウドメモリデータの移行 & 管理 |
| **MCPツール** | MCPツールのグラフィカル管理 |
| **エージェントスキル** | コミュニティスキルのワンクリックインストール |
| **モデルチャージ** | Nagaポータルのクレジットチャージ |

---

## 6. ターミナル設定 · ConfigView

設定ページは3つのタブを持つ単一ページにリデザインされました（3-in-1統一）：

| タブ | 内容 |
|-----|---------|
| **モデル接続** | LLM APIキー、ベースURL、モデル選択 |
| **メモリ接続** | Neo4j接続パラメータ、NagaMemoryクラウド設定 |
| **音声/ビジュアル設定** | キャラクタープロファイル、Live2Dモデル & SSAA、TTS音声、チャットフォントサイズ |

### キャラクターカードシステム

`characters/`ディレクトリが切り替え可能なAIキャラクターを管理し、各キャラクターはJSON設定ファイルで記述されます：

```json
{
  "ai_name": "Najezhda",
  "user_name": "User",
  "live2d_model": "NagaTest2/NagaTest2.model3.json",
  "prompt_file": "conversation_style_prompt.txt",
  "portrait": "Naga.png",
  "bio": "開発者 柏斯阔落 が作成したAIアシスタント、愛称Naga。"
}
```

- 各キャラクターディレクトリには独立した会話スタイルプロンプト、Live2Dモデルアセット、ポートレート画像が含まれます
- キャラクターが有効化されると、AI名とLive2Dモデルはキャラクター JSONにより完全に管理され、UIで手動上書きはできません
- デフォルトキャラクター: **Najezhda**

ソース: [`characters/`](characters/)

---

## 7. MusicBox · MusicView

メインインターフェースのBGMと**同じ再生インスタンスを共有する**スタンドアロン音楽プレーヤー（統一BGMアーキテクチャ）：

- **プレイリストエディター**（`MusicEditView`）: トラックリストを管理；保存時にグローバルプレーヤーに即座に同期
- **再生状態同期**: 再生/一時停止アイコンがオーディオイベントとリアルタイムに更新
- **ループ**: 現在のトラック終了時に自動的に次のトラックへ進行
- **Live2Dリップシンク**: TTS再生中、`AdvancedLipSyncEngineV2`が60FPSでLive2Dの口形状を駆動

---

## 8. フローティングボール · FloatingView

メインパネルの「フロート」ボタンをクリックすると、軽量フローティングボールウィンドウに入り、4つの状態を循環します：

```
ball（100×100の円）→ compact（420×100の折りたたみバー）→ full（420×Nの展開）→ classic（通常ウィンドウ）
```

**外観 & アニメーション：**
- スプライトフレーム瞬きアニメーション: 5フレーム（開 → 半閉 → 閉 → 半閉 → 開）、70ms/フレーム、ランダム間隔トリガー
- 返信生成中: 光るハロパルスエフェクト
- ホバー時: 明度リフトエフェクト
- 透明フレームレスウィンドウ、自由にドラッグ可能

**機能：**
- フローティング状態で直接チャット入力可能；compact / full状態でメッセージ履歴を閲覧
- スクリーンショットキャプチャパネル: 画面ウィンドウを画像添付として選択
- ファイルアップロード対応
- 右クリックメニューはElectronネイティブメニューで実装（小窓でのクリッピングを防止）

---

## グローバル機能

### 音声インタラクション

**TTS（テキスト読み上げ）**

- エンジン: Edge-TTS、OpenAI互換エンドポイント `/v1/audio/speech`
- アーキテクチャ: 3スレッドパイプライン — 文キュー → TTS呼び出し（Semaphore(2)並行）→ pygame再生
- Live2Dリップシンク: 60FPSで5パラメータを抽出（mouth_open / mouth_form / mouth_smile / eye_brow_up / eye_wide）
- ポートクリーンアップ: 起動時に占有ポートを自動検出・解放

**ASR（音声認識）**

- ローカルエンジン: FunASR、VADエンドポイント検出とWebSocketリアルタイムストリーミング
- 3モード自動切替: `LOCAL`（FunASR）→ `END_TO_END`（Qwen Omni）→ `HYBRID`

**リアルタイム音声チャット**（DashScope APIキーが必要）

- Qwen Omni経由の全二重WebSocket音声インタラクション
- エコー抑制、VAD検出、オーディオチャンキング（200ms）、セッションクールダウン制御

```json
{
  "voice_realtime": {
    "enabled": true,
    "provider": "qwen",
    "api_key": "your-dashscope-key",
    "model": "qwen3-omni-flash-realtime"
  }
}
```

ソース: [`voice/`](voice/)

---

### Live2Dアバター

**pixi-live2d-display** + **PixiJS WebGL**を使用してCubism Live2Dモデルをレンダリング。
SSAAスーパーサンプリング: Canvasを`width × ssaa`でレンダリングし、CSS `transform: scale(1/ssaa)`。

**4チャンネル直交アニメーションシステム**（`live2dController.ts`）：

| チャンネル | 制御対象 | 特徴 |
|---------|----------|---------|
| **ボディステート** | idle / thinking / talkingループ | エルミート滑らか補間、`naga-actions.json`から読み込み |
| **アクション** | うなずき/首振りなどの頭部アクション | FIFOキュー、単一実行 |
| **感情** | `.exp3.json`表情ファイル | Add / Multiply / Overwriteブレンドモード、指数減衰遷移 |
| **トラッキング** | マウス視線追従 | `tracking_hold_delay_ms`で開始遅延を設定可能 |

マージ順序: ボディステート → 口 → アクション → 手動オーバーライド → 感情ブレンド → トラッキングブレンド

---

### OpenClawコンピュータ制御

OpenClaw Gateway（ポート20789）と連携し、自然言語でAIコーディングアシスタントにローカルタスクを委託します。

- **3層フォールバック起動：** パッケージバイナリ → グローバル`openclaw`コマンド → 自動`npm install -g openclaw`
- sessionKeyフック（2026.2.17+）対応、カスタムフックパスの設定可能
- `POST /openclaw/send`で命令を送信、最大120秒待機

**タスクスケジューラ（`TaskScheduler`）：**
- タスクステップの記録（目的/内容/出力/分析/成功状態）
- 「重要な発見」マーカーの自動抽出
- メモリ圧縮: ステップがしきい値を超えると、LLMが`CompressedMemory`を生成（key_findings / failed_attempts / current_status / next_steps）
- `schedule_parallel_execution()`が`asyncio.gather()`でタスクリストを並列実行

ソース: [`agentserver/`](agentserver/)

---

### スプラッシュアニメーション

| フェーズ | 内容 |
|-------|---------|
| **タイトルフェーズ** | 黒オーバーレイ + 40個の金色上昇パーティクル + タイトル画像2.4秒CSSキーフレーム；タイトル表示時にウェイクボイス再生 |
| **プログレスフェーズ** | ニューラルネットワークパーティクル背景 + Live2D切り抜きフレーム + 金色プログレスバー（`requestAnimationFrame`補間、最低速度0.5フロア） |
| **停滞検出** | 3秒間進捗なしで再起動ヒントを表示；25%以降は毎秒バックエンド`/health`をポーリング |
| **覚醒** | 進捗が100%に達すると脈動する「クリックして覚醒」プロンプトが表示 |

---

## バックエンドアーキテクチャ

NagaAgentは5つの独立したマイクロサービスで構成され、すべて`main.py`によってオーケストレーションされます：

```
┌─────────────────────────────────────────────────────────┐
│                   Electron / PyQt5 フロントエンド          │
│  Vue 3 + Vite + UnoCSS + PrimeVue + pixi-live2d-display │
│                                                         │
│  PanelView · MessageView · MindView · SkillView         │
│  MarketView · ConfigView · MusicView · FloatingView     │
│  ForumListView · ForumPostView · ForumQuotaView …       │
└──────────┬─────────────┬──────────────┬─────────────────┘
           │             │              │
   ┌───────▼──────┐ ┌────▼────┐  ┌─────▼──────┐
   │  API Server  │ │  Agent  │  │   Voice    │
   │   :8000      │ │  Server │  │  Service   │
   │              │ │  :8001  │  │   :5048    │
   │ チャット/SSE │ │         │  │            │
   │ ツールコール │ │ タスク  │  │ TTS / ASR  │
   │ 圧縮        │ │ スケジュ│  │ リアルタイム│
   │ ドキュメント │ │ ール    │  │ 音声       │
   │ 認証プロキシ │ │ OpenClaw│  │            │
   │ メモリAPI   │ └────┬────┘  └────────────┘
   │ スキルマーケ │      │
   │ ット        │  ┌───▼──────────┐
   │ 設定管理    │  │  OpenClaw    │
   └──────┬───────┘  │  Gateway     │
          │          │  :20789      │
   ┌──────▼──────┐   └─────────────┘
   │ MCP Server  │
   │   :8003     │
   │ ツール登録  │
   │ エージェント│
   │ ディスカバリ│
   │ 並列実行    │
   └──────┬──────┘
          │
  ┌───────┴───────────────────────┐
  │      MCPエージェント（プラグイン） │
  │ Weather | Search | Crawl      │
  │ Launcher | Guide | Doc | MQTT │
  └───────────────────────────────┘
          │
   ┌──────▼──────┐
   │    Neo4j    │
   │   :7687     │
   │  ナレッジ    │
   │   グラフ     │
   └─────────────┘
```

### ディレクトリ構造

```
NagaAgent/
├── main.py                   # 統一エントリーポイント、全サービスをオーケストレーション
├── build.py                  # クロスプラットフォームビルドスクリプト
├── config.json               # ランタイム設定（config.json.exampleからコピー）
├── pyproject.toml            # バージョン5.1.0、プロジェクトメタデータ & 依存関係
│
├── apiserver/                # API Server (:8000)
│   ├── api_server.py         #   FastAPIメインアプリ
│   ├── agentic_tool_loop.py  #   マルチラウンドツールコールループ
│   ├── llm_service.py        #   LiteLLM統一LLMインターフェース
│   └── streaming_tool_extractor.py  # ストリーミング文分割 + TTSディスパッチ
│
├── agentserver/              # Agent Server (:8001)
│   ├── agent_server.py
│   └── task_scheduler.py     #   タスクオーケストレーション + 圧縮メモリ
│
├── mcpserver/                # MCP Server (:8003)
│   ├── mcp_server.py
│   ├── mcp_registry.py       #   マニフェストスキャン + 動的登録
│   ├── mcp_manager.py        #   unified_call() ルーティング
│   ├── agent_weather_time/
│   ├── agent_open_launcher/
│   ├── agent_game_guide/
│   ├── agent_online_search/
│   ├── agent_crawl4ai/
│   ├── agent_playwright_master/
│   ├── agent_vision/
│   ├── agent_mqtt_tool/
│   └── agent_office_doc/
│
├── summer_memory/            # GRAGナレッジグラフメモリ
│   ├── quintuple_extractor.py  #   OpenAI / Anthropicフォーマット対応
│   ├── quintuple_graph.py
│   ├── quintuple_rag_query.py
│   ├── task_manager.py
│   ├── memory_manager.py
│   └── memory_client.py      #   NagaMemoryリモートクライアント
│
├── voice/                    # 音声サービス (:5048 / :5060)
│   ├── output/               #   TTS + リップシンク
│   └── input/                #   ASR + リアルタイム音声
│
├── characters/               # キャラクター設定ディレクトリ
│   └── Najezhda/             #   プロンプト / Live2Dモデル / ポートレート
│
├── frontend/                 # Electron + Vue 3 フロントエンド
│   ├── electron/             #   メインプロセス
│   │   └── modules/          #   backend / hotkeys / menu / tray / updater / window
│   └── src/
│       ├── views/            #   全ページビュー
│       ├── forum/            #   フォーラムモジュール
│       ├── components/       #   共通コンポーネント
│       ├── composables/      #   useAuth / useBackground / useAudio …
│       └── utils/            #   live2dController / session / config
│
├── system/                   # 設定ローダー、環境チェッカー、システムプロンプト
├── guide_engine/             # ゲームガイドエンジン
└── logs/                     # ランタイムログ、ナレッジグラフファイル
```

---

## オプション設定

<details>
<summary><b>ナレッジグラフメモリ（Neo4j）</b></summary>

Neo4jをインストール（[Docker](https://hub.docker.com/_/neo4j)または[Neo4j Desktop](https://neo4j.com/download/)）し、`config.json`を設定してください：

```json
{
  "grag": {
    "enabled": true,
    "neo4j_uri": "neo4j://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "your-password"
  }
}
```

Neo4jなしの場合、GRAGはローカルJSONファイルストレージのみを使用します — 機能に影響はありません。
</details>

<details>
<summary><b>音声インタラクション（TTS / ASR）</b></summary>

```json
{
  "system": { "voice_enabled": true },
  "tts": {
    "port": 5048,
    "default_voice": "zh-CN-XiaoxiaoNeural"
  }
}
```

全二重リアルタイム音声チャット（Qwen DashScope APIキーが必要）：

```json
{
  "voice_realtime": {
    "enabled": true,
    "provider": "qwen",
    "api_key": "your-dashscope-key",
    "model": "qwen3-omni-flash-realtime"
  }
}
```
</details>

<details>
<summary><b>Live2Dアバター（カスタムモデル）</b></summary>

```json
{
  "web_live2d": {
    "ssaa": 2,
    "model": {
      "source": "./models/your-model/model.model3.json",
      "x": 0.5,
      "y": 1.3,
      "size": 6800
    },
    "face_y_ratio": 0.13,
    "tracking_hold_delay_ms": 100
  }
}
```

キャラクターカードが有効な場合、`ai_name`と`model.source`はキャラクターJSONによって自動的に上書きされます — 手動編集は不要です。
</details>

<details>
<summary><b>MQTT IoT制御</b></summary>

```json
{
  "mqtt": {
    "enabled": true,
    "broker": "mqtt-broker-address",
    "port": 1883,
    "topic": "naga/agent/topic",
    "client_id": "naga-agent-client"
  }
}
```
</details>

---

## ポート

| サービス | ポート | 説明 |
|---------|------|-------------|
| API Server | 8000 | メインインターフェース: チャット、設定、認証、スキルマーケット |
| Agent Server | 8001 | タスクスケジューリング、OpenClaw |
| MCP Server | 8003 | MCPツール登録 & ディスパッチ |
| Memory Server | 8004 | メモリサービス |
| 音声サービス | 5048 | TTS / ASR |
| Neo4j | 7687 | ナレッジグラフ（オプション） |
| OpenClaw Gateway | 20789 | AIコンピュータ制御（オプション） |

---

## トラブルシューティング

| 問題 | 解決方法 |
|-------|----------|
| Pythonバージョンエラー | Python 3.11を使用してください；uvによる自動バージョン管理を推奨 |
| ポートが使用中 | 8000、8001、8003、5048が利用可能か確認してください |
| Neo4jタイムアウト / ハング | 2.24で修正済み；Neo4jサービスが起動していることを確認 |
| Neo4j接続状態の誤検知 | 4.12で修正済み：py2neo `Graph()` timeoutパラメータの互換性 |
| TTSが無音 / CORSエラー | 2.25で修正済み；`voice_enabled: true`を確認 |
| プログレスバーが停止 | APIキーを確認；3秒後に再起動ヒントが表示されます |
| フローティングボールのアバターが表示されない | 2.17で修正済み（スプライトフレームパス）；最新のパッケージ版を使用してください |
| config.jsonの文字化け | 2.19で修正済み: config_managerがファイルエンコーディングを自動検出 |
| OpenClawが起動しない | 2.24で修正済み（グローバルモードでの設定ファイル欠落） |

```bash
python main.py --check-env --force-check  # フル環境診断
python main.py --quick-check              # クイックチェック
```

---

## コントリビューション

IssueやPull Requestを歓迎します。ご質問はQQチャンネル **nagaagent1** にご参加ください。

---

## Star履歴

[![Star History Chart](https://api.star-history.com/svg?repos=RTGS2017/NagaAgent&type=date&legend=top-left)](https://www.star-history.com/#RTGS2017/NagaAgent&type=date&legend=top-left)

# 販売実績・分析ダッシュボード（2026年上期 1〜6月）

Barefoot Inc. の店舗別・商品/ブランド別・決済別の売上金額・点数を集計したダッシュボードです。

## 構成

- `dashboard.html` / `index.html` — 完成したダッシュボード本体（自己完結HTML、ブラウザで直接開けます。同一内容で2ファイル。`index.html`はVercel等の静的ホスティングでルートパスが解決されるように用意）
- `data/dashboard_data.json` — ダッシュボードが読み込む集計済みデータ（`dashboard.html` に埋め込み済み）
- `scripts/etl.py` — 17件の生データファイル（Excel/CSV）を正規化して `data/records.json` を生成するETLスクリプト
- `scripts/aggregate.py` — `records.json` を店舗別・ブランド別・月次などに集計し `data/dashboard_data.json` を生成するスクリプト

> 生データ（Excel/CSVの元ファイル）は社外秘のためこのリポジトリには含めていません。
> `scripts/etl.py` はソースファイルパスを再設定すれば再実行できます。

## 画面構成

ダッシュボードは5つのタブで構成:

- **概要** — KPI（総売上・総点数・伝票数・客単価。総点数は靴以外の商品も含む全商品）、月次推移、店舗別売上ランキング、ブランド構成比、決済方法別比率（全体）
- **VFFシューズ** — VFFブランドのうちシューズのみ（ソックス・Furoshiki等を除く）の総足数・月次推移、販売チャネル区分（オンラインストア／直営実店舗＝K Village・Paradise Park／Central百貨店＝CHIDLOM等5店舗＋Coollabo＋VFF Cart LP／イベント／Siam Discovery／委託販売(オフライン)）のシェア、性別セグメント分布（サイズ表記W/Mからの推定値）、モデル別販売ランキング（シリーズ別に集約した横棒グラフ）
- **店舗別** — 店舗・チャネルごとの詳細（月次推移・ブランド構成比・決済方法比率をドロップダウンで切替）、全店舗比較表
- **商品・ブランド別** — 全ブランド合算のモデル別Top10/Worst10ランキング、ブランド別売上詳細（ドロップダウン）、Others内訳
- **このデータについて** — 訂正履歴、未対応データ、集計ルール、ソースファイル一覧

## データ範囲

- 対象期間: 2026年1月〜6月
- 統合ソース: 実店舗6（K Village / Thaniya / Paradise Park / Central Ladprao 3F(Coollabo) / VFF Cart LP / Siam Discovery）、
  Central百貨店内5店舗（CHIDLOM / CHIDLOM ONLINE / CENTRAL WORLD-CDS / LARDPRAO / EASTVILLE）、
  オンライン（BFT・EDV統合、チャネル別内訳あり）、イベント（4ファイル合算）、委託販売（BFT・EDV別集計）

## 既知の制約

- **前年（2025年1〜6月）比較データは未取得** — 届き次第、前年比セクションを追加予定
- **決済方法（Cash/Credit Card/QR）** は「イベント」カテゴリの一部ファイルにのみ記録があり、他店舗・チャネルは未対応
- Central Total Department（百貨店内5店舗）は月次集計のみのため、伝票数・客単価は算出不可

## 訂正履歴

初期報告で「BFT委託」の合計を誤って二重計上していました（元データ末尾の合計行を明細行と誤認）。
正しい値は 658,055.60 THB です（`dashboard.html` の「データについて」タブに記載）。

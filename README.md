# PracticeHell

> 身につくまで、終わらない。

PracticeHell は、LLMが生成する問題を1問ずつ解き、設定された習熟基準の達成を目指すシンプルな演習アプリです。

## 解答者の流れ

1. 参加コードを含むURLへアクセスする（例: `/?code=math-2026`）
2. 出席番号と名前を入力する
3. 生成された問題へ1問ずつ解答する
4. 解答直後に正誤、正答、総解答数、直近N問の正答率を確認する
5. 習熟基準を達成した後も、希望すれば問題を解き続ける

## 基本方針

- 参加コードは問題YAMLの `join_code` と照合する。
- 問題はLLM APIで都度生成し、待ち時間を抑えるため次の1問を先行生成する。
- 問題は文章と式だけで構成し、画像やリッチコンテンツは扱わない。
- 問題定義はYAML、出席情報・生成問題・答案・進捗はSQLiteへ保存する。
- 直近N問の正答率がM%以上になった時点で習熟基準達成とする。
- 画面は白背景と最小限のCSSで構成し、デザインを後から差し替えられるようにする。
- 教師向けリアルタイム進捗画面と、問題YAMLの生成機能は後続開発とする。

問題YAMLの例:

- [数値解答式](problems/example_number_answer.yaml)
- [単一選択式](problems/example_single_choice_answer.yaml)
- [単純な足し算](problems/example_simple_addition.yaml)

## 起動方法

Python 3.12以降、Node.js 20以降を想定しています。

```bash
uv sync
npm install
npm run build
cp -n .env.example .env
uv run --isolated uvicorn practice_hell.asgi:app --reload
```

`.env` の `OPENAI_API_KEY` にAPIキーを設定し、ブラウザで次の形式のURLを開きます。

```text
http://127.0.0.1:8000/?code=test-simple-addition
```

APIを使わずに画面を確認する場合は、`.env` で `QUESTION_PROVIDER=fixed` を指定します。生成問題・答案・進捗は、標準ではルートの `practice-hell.db` に保存されます。

## 確認方法

```bash
uv run --isolated pytest
npm test -- --run
npm run build
```

## 現在の状態

解答者向けの最小実装は完了しています。対象範囲と後続項目は [plan.md](plan.md) を参照してください。

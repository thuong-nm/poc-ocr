# img2docx evaluation — dev-vlm — 12 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng, `primary:vlm`=qwen3-vl[qwen3-vl:2b-instruct-q4_K_M]@http://localhost:11434/v1

## Summary

| metric | value |
|---|---|
| pages | 12 |
| text blocks | 156 |
| CER (micro, strict) | 0.140 |
| CER (diacritics-insensitive) | 0.133 |
| WER (mean) | 0.315 |
| page CER (order-sensitive) | 0.138 |
| block type accuracy | 0.859 |
| table TEDS / TEDS-S | 0.814 / 1.000 (n=12) |
| reading order Kendall τ | 0.929 |
| date extraction acc | 0.650 |
| doc-number extraction acc | 0.667 |
| image element recall | logo 1.00, signature 0.33, stamp 1.00 |
| pages flagged needs_review | 0.92 |
| runtime s/page (mean) | 160.2 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 20 | 0.319 | 0.280 | 0.433 | 0.85 |
| doc_number | 12 | 0.292 | 0.286 | 0.375 | 0.67 |
| footer | 12 | 0.406 | 0.406 | 0.444 | 0.75 |
| handwritten_note | 12 | 0.689 | 0.538 | 1.111 | 0.33 |
| header | 24 | 0.009 | 0.000 | 0.075 | 1.00 |
| paragraph | 60 | 0.110 | 0.108 | 0.187 | 0.93 |
| title | 16 | 0.164 | 0.167 | 0.266 | 1.00 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 96 | 0.182 | 0.169 | 0.415 | 0.80 |
| en | 52 | 0.049 | 0.049 | 0.123 | 0.94 |
| mixed | 8 | 0.266 | 0.262 | 0.358 | 1.00 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| mild | 156 | 0.140 | 0.133 | 0.315 | 0.86 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| mild/ar | 54 | 0.114 | 0.100 | 0.303 | 0.93 |
| mild/en | 48 | 0.056 | 0.055 | 0.146 | 0.94 |
| mild/mixed | 54 | 0.253 | 0.247 | 0.477 | 0.72 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| mild | 0.814 | 1.000 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | mild | 0.072 | 0.962 | 1.00 | 154.2 | True | 0.9043 |
| synth_ar_0102 | mild | 0.119 | 0.577 | 1.00 | 160.9 | True | 0.8362 |
| synth_ar_0103 | mild | 0.186 | 0.670 | 1.00 | 218.4 | True | 0.8296 |
| synth_ar_0104 | mild | 0.048 | 1.000 | 1.00 | 149.8 | True | 0.8942 |
| synth_en_0105 | mild | 0.082 | 1.000 | 0.93 | 171.1 | True | 0.9656 |
| synth_en_0106 | mild | 0.087 | 1.000 | 1.00 | 146.8 | False | 0.9743 |
| synth_en_0107 | mild | 0.023 | 1.000 | 1.00 | 144.7 | True | 0.9478 |
| synth_en_0108 | mild | 0.084 | 1.000 | 0.89 | 133.8 | True | 0.9508 |
| synth_mixed_0109 | mild | 0.244 | 0.631 | 1.00 | 139.7 | True | 0.7706 |
| synth_mixed_0110 | mild | 0.188 | 0.703 | 0.62 | 160.0 | True | 0.8395 |
| synth_mixed_0111 | mild | 0.288 | 0.535 | 0.72 | 181.9 | True | 0.7704 |
| synth_mixed_0112 | mild | 0.235 | 0.689 | 1.00 | 161.1 | True | 0.7976 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/mild | handwritten_note | 2.50 | يحفظ | التاريخية في |
| synth_mixed_0110/mild | handwritten_note | 2.00 | يعتمد | التاريخ. يعد |
| synth_ar_0103/mild | handwritten_note | 1.60 | يعتمد | تعميم إداري |
| synth_en_0108/mild | handwritten_note | 1.38 | Approved | approved according |
| synth_mixed_0111/mild | doc_number | 1.15 | الرقم: ٧/٦٣٨٣ | ٧/٦٣٨٣ : الرقم: كفر |
| synth_en_0108/mild | paragraph | 1.11 | Director General Dr. Sami Abdulrahman | Antiquities Directorate before starting any maintenance |
| synth_ar_0103/mild | doc_number | 1.08 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: بِعْرَى |
| synth_en_0106/mild | paragraph | 1.00 | Director General Dr. Sami Abdulrahman |  |
| synth_mixed_0109/mild | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_mixed_0110/mild | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_mixed_0111/mild | handwritten_note | 1.00 | يحفظ |  |
| synth_mixed_0112/mild | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_ar_0103/mild | footer | 0.93 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ | الرحمن هاتف: ١٢٣٤ - ٤٧٠٠٠٠٠٠٠٠٠٠٠٠٠٠٠٠ |
| synth_mixed_0109/mild | title | 0.92 | بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ | المواقف بِحْرَ إسم الله الرحمن الرحيم الموضوع: |
| synth_ar_0102/mild | date | 0.91 | التاريخ: ١٧/١٢/١٤٤٤ هـ | الرَّاجِعَة التاريخ: ١٧/١٢/١٤٤٤ الموافق: |

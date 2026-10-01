# img2docx evaluation — default config — 12 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng

## Summary

| metric | value |
|---|---|
| pages | 12 |
| text blocks | 156 |
| CER (micro, strict) | 0.180 |
| CER (diacritics-insensitive) | 0.182 |
| WER (mean) | 0.405 |
| page CER (order-sensitive) | 0.146 |
| block type accuracy | 0.801 |
| table TEDS / TEDS-S | 0.814 / 1.000 (n=12) |
| reading order Kendall τ | 0.898 |
| date extraction acc | 0.400 |
| doc-number extraction acc | 0.500 |
| image element recall | logo 1.00, signature 0.33, stamp 1.00 |
| pages flagged needs_review | 1.00 |
| runtime s/page (mean) | 17.4 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 20 | 0.429 | 0.426 | 0.617 | 0.70 |
| doc_number | 12 | 0.548 | 0.548 | 0.583 | 0.58 |
| footer | 12 | 0.397 | 0.397 | 0.444 | 0.67 |
| handwritten_note | 12 | 0.660 | 0.660 | 1.403 | 0.25 |
| header | 24 | 0.000 | 0.000 | 0.000 | 1.00 |
| paragraph | 60 | 0.138 | 0.137 | 0.261 | 0.92 |
| title | 16 | 0.343 | 0.383 | 0.375 | 0.88 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 96 | 0.255 | 0.258 | 0.547 | 0.70 |
| en | 52 | 0.066 | 0.066 | 0.173 | 0.96 |
| mixed | 8 | 0.203 | 0.203 | 0.207 | 1.00 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| mild | 156 | 0.180 | 0.182 | 0.405 | 0.80 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| mild/ar | 54 | 0.167 | 0.173 | 0.428 | 0.83 |
| mild/en | 48 | 0.073 | 0.073 | 0.188 | 0.96 |
| mild/mixed | 54 | 0.303 | 0.303 | 0.576 | 0.63 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| mild | 0.814 | 1.000 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | mild | 0.055 | 0.962 | 1.00 | 15.4 | True | 0.9026 |
| synth_ar_0102 | mild | 0.129 | 0.577 | 1.00 | 20.0 | True | 0.8518 |
| synth_ar_0103 | mild | 0.179 | 0.670 | 1.00 | 19.6 | True | 0.8617 |
| synth_ar_0104 | mild | 0.099 | 1.000 | 1.00 | 15.7 | True | 0.8906 |
| synth_en_0105 | mild | 0.134 | 1.000 | 0.93 | 19.3 | True | 0.9423 |
| synth_en_0106 | mild | 0.051 | 1.000 | 1.00 | 17.3 | True | 0.9494 |
| synth_en_0107 | mild | 0.081 | 1.000 | 1.00 | 15.1 | True | 0.9563 |
| synth_en_0108 | mild | 0.098 | 1.000 | 1.00 | 16.0 | True | 0.9237 |
| synth_mixed_0109 | mild | 0.355 | 0.631 | 0.69 | 19.9 | True | 0.6932 |
| synth_mixed_0110 | mild | 0.198 | 0.703 | 0.70 | 16.7 | True | 0.8442 |
| synth_mixed_0111 | mild | 0.140 | 0.535 | 0.78 | 17.4 | True | 0.7885 |
| synth_mixed_0112 | mild | 0.233 | 0.689 | 0.69 | 16.9 | True | 0.8256 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/mild | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_ar_0102/mild | doc_number | 1.77 | الرقم: ٩/٨٦١٣ | Directorate تم الرقم: التاريخ: |
| synth_ar_0103/mild | handwritten_note | 1.40 | يعتمد | إداري تعمل |
| synth_mixed_0110/mild | doc_number | 1.38 | الرقم: ١/٢٠٠٥ | ١/٠٠١6 الرقم: yy التاريخ: |
| synth_mixed_0111/mild | doc_number | 1.38 | الرقم: ٧/٦٣٨٣ | Directorate الرقم: [؟] |
| synth_mixed_0112/mild | date | 1.29 | الموافق: ١٧/٠٤/٢٠٢٥ م | 17/01/١561 ه الموافق: [؟] م لامتابعة |
| synth_mixed_0110/mild | handwritten_note | 1.20 | يعتمد | يعقد مؤتمر |
| synth_mixed_0112/mild | doc_number | 1.15 | الرقم: ٤/٧٥٧١ | t/VoV) الرقم: التاريخ: |
| synth_ar_0102/mild | handwritten_note | 1.00 | تمت المراجعة | كت الراجعة الموضوع: |
| synth_ar_0103/mild | doc_number | 1.00 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: يعر |
| synth_ar_0103/mild | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_mixed_0109/mild | handwritten_note | 1.00 | يعتمد | مم يعقد |
| synth_mixed_0109/mild | title | 1.00 | بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ |  |
| synth_mixed_0109/mild | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_mixed_0110/mild | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |

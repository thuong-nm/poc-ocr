# img2docx evaluation — default config — 36 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng

## Summary

| metric | value |
|---|---|
| pages | 36 |
| text blocks | 468 |
| CER (micro, strict) | 0.213 |
| CER (diacritics-insensitive) | 0.215 |
| WER (mean) | 0.454 |
| page CER (order-sensitive) | 0.221 |
| block type accuracy | 0.718 |
| table TEDS / TEDS-S | 0.788 / 1.000 (n=36) |
| reading order Kendall τ | 0.838 |
| date extraction acc | 0.400 |
| doc-number extraction acc | 0.500 |
| image element recall | logo 1.00, signature 0.14, stamp 0.75 |
| pages flagged needs_review | 1.00 |
| runtime s/page (mean) | 35.6 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 60 | 0.453 | 0.454 | 0.628 | 0.58 |
| doc_number | 36 | 0.518 | 0.518 | 0.528 | 0.53 |
| footer | 36 | 0.436 | 0.436 | 0.477 | 0.58 |
| handwritten_note | 36 | 0.704 | 0.704 | 1.259 | 0.39 |
| header | 72 | 0.049 | 0.049 | 0.067 | 0.86 |
| paragraph | 180 | 0.169 | 0.168 | 0.329 | 0.93 |
| title | 48 | 0.397 | 0.434 | 0.615 | 0.35 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 288 | 0.303 | 0.306 | 0.630 | 0.56 |
| en | 156 | 0.079 | 0.079 | 0.153 | 0.97 |
| mixed | 24 | 0.235 | 0.235 | 0.299 | 0.96 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| clean | 156 | 0.234 | 0.236 | 0.489 | 0.72 |
| hard | 156 | 0.217 | 0.218 | 0.440 | 0.71 |
| mild | 156 | 0.190 | 0.192 | 0.435 | 0.73 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| clean/ar | 54 | 0.257 | 0.261 | 0.592 | 0.65 |
| clean/en | 48 | 0.078 | 0.078 | 0.109 | 0.98 |
| clean/mixed | 54 | 0.369 | 0.371 | 0.723 | 0.56 |
| hard/ar | 54 | 0.203 | 0.205 | 0.460 | 0.65 |
| hard/en | 48 | 0.107 | 0.107 | 0.211 | 0.96 |
| hard/mixed | 54 | 0.344 | 0.347 | 0.622 | 0.54 |
| mild/ar | 54 | 0.175 | 0.181 | 0.469 | 0.70 |
| mild/en | 48 | 0.081 | 0.081 | 0.186 | 0.98 |
| mild/mixed | 54 | 0.319 | 0.320 | 0.622 | 0.54 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| clean | 0.765 | 1.000 |
| hard | 0.786 | 1.000 |
| mild | 0.814 | 1.000 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | clean | 0.162 | 0.793 | 0.69 | 36.2 | True | 0.859 |
| synth_ar_0101 | hard | 0.254 | 0.950 | 0.71 | 55.5 | True | 0.8503 |
| synth_ar_0101 | mild | 0.108 | 0.962 | 0.75 | 38.6 | True | 0.8944 |
| synth_ar_0102 | clean | 0.287 | 0.665 | 0.79 | 43.0 | True | 0.7966 |
| synth_ar_0102 | hard | 0.352 | 0.500 | 0.96 | 58.7 | True | 0.8033 |
| synth_ar_0102 | mild | 0.148 | 0.577 | 1.00 | 46.4 | True | 0.8409 |
| synth_ar_0103 | clean | 0.298 | 0.632 | 0.66 | 40.8 | True | 0.8397 |
| synth_ar_0103 | hard | 0.308 | 0.670 | 0.74 | 43.5 | True | 0.8176 |
| synth_ar_0103 | mild | 0.315 | 0.670 | 0.97 | 38.3 | True | 0.8625 |
| synth_ar_0104 | clean | 0.212 | 0.812 | 0.71 | 40.3 | True | 0.8884 |
| synth_ar_0104 | hard | 0.232 | 0.962 | 0.68 | 40.0 | True | 0.8886 |
| synth_ar_0104 | mild | 0.123 | 1.000 | 0.95 | 29.9 | True | 0.8696 |
| synth_en_0105 | clean | 0.330 | 1.000 | 0.93 | 37.5 | True | 0.8619 |
| synth_en_0105 | hard | 0.136 | 1.000 | 0.93 | 32.5 | True | 0.9546 |
| synth_en_0105 | mild | 0.134 | 1.000 | 0.93 | 31.2 | True | 0.9558 |
| synth_en_0106 | clean | 0.087 | 1.000 | 1.00 | 35.8 | True | 0.9408 |
| synth_en_0106 | hard | 0.095 | 1.000 | 1.00 | 36.0 | True | 0.9418 |
| synth_en_0106 | mild | 0.067 | 1.000 | 1.00 | 32.4 | True | 0.9478 |
| synth_en_0107 | clean | 0.064 | 1.000 | 1.00 | 26.6 | True | 0.9536 |
| synth_en_0107 | hard | 0.093 | 0.903 | 1.00 | 29.2 | True | 0.9145 |
| synth_en_0107 | mild | 0.060 | 1.000 | 1.00 | 29.4 | True | 0.9583 |
| synth_en_0108 | clean | 0.073 | 1.000 | 0.89 | 26.5 | True | 0.9637 |
| synth_en_0108 | hard | 0.149 | 0.909 | 0.89 | 25.8 | True | 0.9123 |
| synth_en_0108 | mild | 0.131 | 1.000 | 0.89 | 28.3 | True | 0.93 |
| synth_mixed_0109 | clean | 0.395 | 0.613 | 0.96 | 36.7 | True | 0.7531 |
| synth_mixed_0109 | hard | 0.452 | 0.585 | 0.94 | 32.3 | True | 0.701 |
| synth_mixed_0109 | mild | 0.406 | 0.631 | 0.96 | 36.4 | True | 0.7291 |
| synth_mixed_0110 | clean | 0.350 | 0.596 | 0.66 | 35.4 | True | 0.7682 |
| synth_mixed_0110 | hard | 0.186 | 0.670 | 0.68 | 28.7 | True | 0.8366 |
| synth_mixed_0110 | mild | 0.235 | 0.703 | 0.65 | 30.1 | True | 0.8433 |
| synth_mixed_0111 | clean | 0.239 | 0.517 | 0.66 | 33.1 | True | 0.7409 |
| synth_mixed_0111 | hard | 0.213 | 0.634 | 0.69 | 30.5 | True | 0.8186 |
| synth_mixed_0111 | mild | 0.170 | 0.535 | 0.78 | 30.5 | True | 0.7859 |
| synth_mixed_0112 | clean | 0.399 | 0.554 | 0.79 | 43.8 | True | 0.6655 |
| synth_mixed_0112 | hard | 0.359 | 0.654 | 0.69 | 27.2 | True | 0.7993 |
| synth_mixed_0112 | mild | 0.348 | 0.689 | 0.65 | 34.6 | True | 0.8293 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/clean | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_ar_0104/mild | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_mixed_0109/clean | handwritten_note | 2.40 | يعتمد | التاريخية سيتم |
| synth_mixed_0110/clean | handwritten_note | 2.20 | يعتمد | ولن يتم النظر |
| synth_mixed_0110/hard | handwritten_note | 2.20 | يعتمد | ولن يتم النظر |
| synth_ar_0103/clean | handwritten_note | 1.60 | يعتمد | الجاري. تم |
| synth_ar_0103/hard | handwritten_note | 1.60 | يعتمد | الجاري. تم |
| synth_mixed_0109/mild | doc_number | 1.54 | الرقم: ٤/٧٤٨٨ | الوطني الرقم: 1/0 75/07/١448 |
| synth_ar_0104/hard | handwritten_note | 1.50 | يحفظ | المتاحف |
| synth_ar_0103/mild | doc_number | 1.46 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: يعر التاريخ: |
| synth_mixed_0111/mild | doc_number | 1.38 | الرقم: ٧/٦٣٨٣ | Directorate الرقم: [؟] |
| synth_en_0108/hard | handwritten_note | 1.38 | Approved | approved according |
| synth_en_0108/mild | handwritten_note | 1.38 | Approved | approved according |
| synth_mixed_0109/clean | date | 1.33 | الموافق: ١٩/٠٥/٢٠٢٦ م | 75/٠7/١448 ZL ه الموافق: [؟] م يعر |
| synth_ar_0102/hard | doc_number | 1.31 | الرقم: ٩/٨٦١٣ | 9 الرقم: 11١772117156646 |

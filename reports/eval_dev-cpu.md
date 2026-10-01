# img2docx evaluation — dev-cpu — 36 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng

## Summary

| metric | value |
|---|---|
| pages | 36 |
| text blocks | 468 |
| CER (micro, strict) | 0.192 |
| CER (diacritics-insensitive) | 0.194 |
| WER (mean) | 0.417 |
| page CER (order-sensitive) | 0.170 |
| block type accuracy | 0.782 |
| table TEDS / TEDS-S | 0.788 / 1.000 (n=36) |
| reading order Kendall τ | 0.908 |
| date extraction acc | 0.400 |
| doc-number extraction acc | 0.500 |
| image element recall | logo 1.00, signature 0.39, stamp 1.00 |
| pages flagged needs_review | 1.00 |
| runtime s/page (mean) | 18.8 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 60 | 0.457 | 0.458 | 0.628 | 0.65 |
| doc_number | 36 | 0.540 | 0.540 | 0.569 | 0.56 |
| footer | 36 | 0.436 | 0.436 | 0.477 | 0.58 |
| handwritten_note | 36 | 0.704 | 0.704 | 1.301 | 0.31 |
| header | 72 | 0.001 | 0.001 | 0.008 | 1.00 |
| paragraph | 180 | 0.151 | 0.150 | 0.296 | 0.91 |
| title | 48 | 0.342 | 0.383 | 0.401 | 0.81 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 288 | 0.276 | 0.280 | 0.573 | 0.68 |
| en | 156 | 0.064 | 0.064 | 0.149 | 0.95 |
| mixed | 24 | 0.222 | 0.222 | 0.288 | 0.96 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| clean | 156 | 0.196 | 0.199 | 0.436 | 0.76 |
| hard | 156 | 0.201 | 0.203 | 0.411 | 0.78 |
| mild | 156 | 0.180 | 0.182 | 0.405 | 0.80 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| clean/ar | 54 | 0.212 | 0.218 | 0.485 | 0.76 |
| clean/en | 48 | 0.054 | 0.054 | 0.143 | 0.94 |
| clean/mixed | 54 | 0.326 | 0.328 | 0.648 | 0.61 |
| hard/ar | 54 | 0.176 | 0.179 | 0.417 | 0.78 |
| hard/en | 48 | 0.088 | 0.088 | 0.163 | 0.94 |
| hard/mixed | 54 | 0.344 | 0.347 | 0.626 | 0.65 |
| mild/ar | 54 | 0.167 | 0.173 | 0.428 | 0.83 |
| mild/en | 48 | 0.073 | 0.073 | 0.188 | 0.96 |
| mild/mixed | 54 | 0.303 | 0.303 | 0.576 | 0.63 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| clean | 0.765 | 1.000 |
| hard | 0.786 | 1.000 |
| mild | 0.814 | 1.000 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | clean | 0.151 | 0.793 | 1.00 | 18.0 | True | 0.8861 |
| synth_ar_0101 | hard | 0.110 | 0.950 | 0.75 | 17.6 | True | 0.8525 |
| synth_ar_0101 | mild | 0.055 | 0.962 | 1.00 | 15.7 | True | 0.9026 |
| synth_ar_0102 | clean | 0.167 | 0.665 | 1.00 | 18.8 | True | 0.8059 |
| synth_ar_0102 | hard | 0.242 | 0.500 | 1.00 | 25.1 | True | 0.8083 |
| synth_ar_0102 | mild | 0.129 | 0.577 | 1.00 | 24.2 | True | 0.8518 |
| synth_ar_0103 | clean | 0.207 | 0.632 | 1.00 | 25.0 | True | 0.8437 |
| synth_ar_0103 | hard | 0.162 | 0.670 | 1.00 | 23.9 | True | 0.8221 |
| synth_ar_0103 | mild | 0.179 | 0.670 | 1.00 | 21.7 | True | 0.8617 |
| synth_ar_0104 | clean | 0.113 | 0.812 | 0.95 | 17.0 | True | 0.897 |
| synth_ar_0104 | hard | 0.128 | 0.962 | 1.00 | 17.1 | True | 0.8856 |
| synth_ar_0104 | mild | 0.099 | 1.000 | 1.00 | 15.8 | True | 0.8906 |
| synth_en_0105 | clean | 0.355 | 1.000 | 0.93 | 22.7 | True | 0.852 |
| synth_en_0105 | hard | 0.152 | 1.000 | 0.93 | 20.0 | True | 0.9273 |
| synth_en_0105 | mild | 0.134 | 1.000 | 0.93 | 21.0 | True | 0.9423 |
| synth_en_0106 | clean | 0.051 | 1.000 | 1.00 | 17.1 | True | 0.953 |
| synth_en_0106 | hard | 0.095 | 1.000 | 1.00 | 17.2 | True | 0.9437 |
| synth_en_0106 | mild | 0.051 | 1.000 | 1.00 | 17.6 | True | 0.9494 |
| synth_en_0107 | clean | 0.076 | 1.000 | 1.00 | 14.4 | True | 0.9372 |
| synth_en_0107 | hard | 0.100 | 0.903 | 1.00 | 16.1 | True | 0.9187 |
| synth_en_0107 | mild | 0.081 | 1.000 | 1.00 | 15.1 | True | 0.9563 |
| synth_en_0108 | clean | 0.051 | 1.000 | 1.00 | 17.1 | True | 0.9569 |
| synth_en_0108 | hard | 0.147 | 0.909 | 0.89 | 14.9 | True | 0.9115 |
| synth_en_0108 | mild | 0.098 | 1.000 | 1.00 | 16.1 | True | 0.9237 |
| synth_mixed_0109 | clean | 0.302 | 0.613 | 1.00 | 19.5 | True | 0.7537 |
| synth_mixed_0109 | hard | 0.385 | 0.585 | 1.00 | 19.2 | True | 0.6912 |
| synth_mixed_0109 | mild | 0.355 | 0.631 | 0.69 | 20.1 | True | 0.6932 |
| synth_mixed_0110 | clean | 0.252 | 0.596 | 0.66 | 18.8 | True | 0.7696 |
| synth_mixed_0110 | hard | 0.169 | 0.670 | 0.68 | 18.1 | True | 0.8277 |
| synth_mixed_0110 | mild | 0.198 | 0.703 | 0.70 | 17.0 | True | 0.8442 |
| synth_mixed_0111 | clean | 0.174 | 0.517 | 0.70 | 18.4 | True | 0.7524 |
| synth_mixed_0111 | hard | 0.211 | 0.634 | 0.70 | 17.4 | True | 0.7934 |
| synth_mixed_0111 | mild | 0.140 | 0.535 | 0.78 | 17.3 | True | 0.7885 |
| synth_mixed_0112 | clean | 0.301 | 0.554 | 1.00 | 25.2 | True | 0.6688 |
| synth_mixed_0112 | hard | 0.253 | 0.654 | 0.72 | 19.9 | True | 0.7985 |
| synth_mixed_0112 | mild | 0.233 | 0.689 | 0.69 | 16.9 | True | 0.8256 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/clean | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_ar_0104/mild | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_ar_0104/hard | handwritten_note | 2.50 | يحفظ | التاريخية في |
| synth_mixed_0109/clean | handwritten_note | 2.40 | يعتمد | التاريخية سيتم |
| synth_mixed_0110/hard | handwritten_note | 2.20 | يعتمد | ولن يتم النظر |
| synth_mixed_0110/clean | handwritten_note | 2.00 | يعتمد | الطلبات يعقد |
| synth_ar_0102/mild | doc_number | 1.77 | الرقم: ٩/٨٦١٣ | Directorate تم الرقم: التاريخ: |
| synth_ar_0103/hard | handwritten_note | 1.60 | يعتمد | تعميم إداري |
| synth_mixed_0112/hard | doc_number | 1.46 | الرقم: ٤/٧٥٧١ | Directorate الرقم: ١لاه//؟ |
| synth_ar_0103/clean | handwritten_note | 1.40 | يعتمد | إداري تعمل |
| synth_ar_0103/mild | handwritten_note | 1.40 | يعتمد | إداري تعمل |
| synth_ar_0103/clean | doc_number | 1.38 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: ae التاريخ: |
| synth_mixed_0109/hard | doc_number | 1.38 | الرقم: ٤/٧٤٨٨ | Directorate الرقم: ححا ال |
| synth_mixed_0110/mild | doc_number | 1.38 | الرقم: ١/٢٠٠٥ | ١/٠٠١6 الرقم: yy التاريخ: |
| synth_mixed_0111/mild | doc_number | 1.38 | الرقم: ٧/٦٣٨٣ | Directorate الرقم: [؟] |

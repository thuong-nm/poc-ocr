# img2docx evaluation — dev-cpu — 36 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng

## Summary

| metric | value |
|---|---|
| pages | 36 |
| text blocks | 468 |
| CER (micro, strict) | 0.204 |
| CER (diacritics-insensitive) | 0.206 |
| WER (mean) | 0.453 |
| page CER (order-sensitive) | 0.180 |
| block type accuracy | 0.750 |
| table TEDS / TEDS-S | 0.788 / 1.000 (n=36) |
| reading order Kendall τ | 0.898 |
| date extraction acc | 0.400 |
| doc-number extraction acc | 0.500 |
| image element recall | logo 1.00, signature 0.19, stamp 0.81 |
| pages flagged needs_review | 0.97 |
| runtime s/page (mean) | 35.2 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 60 | 0.458 | 0.461 | 0.633 | 0.58 |
| doc_number | 36 | 0.558 | 0.558 | 0.542 | 0.53 |
| footer | 36 | 0.436 | 0.436 | 0.477 | 0.58 |
| handwritten_note | 36 | 0.667 | 0.667 | 1.315 | 0.33 |
| header | 72 | 0.001 | 0.001 | 0.008 | 1.00 |
| paragraph | 180 | 0.164 | 0.163 | 0.330 | 0.90 |
| title | 48 | 0.401 | 0.438 | 0.625 | 0.62 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 288 | 0.290 | 0.294 | 0.623 | 0.62 |
| en | 156 | 0.073 | 0.073 | 0.162 | 0.96 |
| mixed | 24 | 0.236 | 0.236 | 0.299 | 0.96 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| clean | 156 | 0.214 | 0.216 | 0.477 | 0.72 |
| hard | 156 | 0.212 | 0.214 | 0.439 | 0.77 |
| mild | 156 | 0.187 | 0.189 | 0.443 | 0.76 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| clean/ar | 54 | 0.228 | 0.232 | 0.544 | 0.69 |
| clean/en | 48 | 0.071 | 0.071 | 0.143 | 0.96 |
| clean/mixed | 54 | 0.345 | 0.347 | 0.707 | 0.56 |
| hard/ar | 54 | 0.190 | 0.193 | 0.489 | 0.74 |
| hard/en | 48 | 0.101 | 0.101 | 0.191 | 0.96 |
| hard/mixed | 54 | 0.349 | 0.353 | 0.611 | 0.63 |
| mild/ar | 54 | 0.163 | 0.168 | 0.465 | 0.76 |
| mild/en | 48 | 0.073 | 0.073 | 0.203 | 0.96 |
| mild/mixed | 54 | 0.330 | 0.332 | 0.633 | 0.57 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| clean | 0.765 | 1.000 |
| hard | 0.786 | 1.000 |
| mild | 0.814 | 1.000 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | clean | 0.162 | 0.793 | 0.69 | 46.5 | True | 0.859 |
| synth_ar_0101 | hard | 0.101 | 0.950 | 1.00 | 45.0 | True | 0.8479 |
| synth_ar_0101 | mild | 0.074 | 0.962 | 1.00 | 55.5 | True | 0.8734 |
| synth_ar_0102 | clean | 0.167 | 0.665 | 1.00 | 55.9 | True | 0.8002 |
| synth_ar_0102 | hard | 0.264 | 0.500 | 1.00 | 91.3 | True | 0.8014 |
| synth_ar_0102 | mild | 0.148 | 0.577 | 1.00 | 82.0 | True | 0.8409 |
| synth_ar_0103 | clean | 0.236 | 0.632 | 1.00 | 39.9 | True | 0.8397 |
| synth_ar_0103 | hard | 0.217 | 0.670 | 1.00 | 59.2 | True | 0.8165 |
| synth_ar_0103 | mild | 0.200 | 0.670 | 1.00 | 47.7 | True | 0.8625 |
| synth_ar_0104 | clean | 0.140 | 0.812 | 0.71 | 37.2 | True | 0.8884 |
| synth_ar_0104 | hard | 0.173 | 0.962 | 0.94 | 35.5 | True | 0.8567 |
| synth_ar_0104 | mild | 0.123 | 1.000 | 0.95 | 34.1 | True | 0.8696 |
| synth_en_0105 | clean | 0.330 | 1.000 | 0.93 | 49.1 | True | 0.8619 |
| synth_en_0105 | hard | 0.133 | 1.000 | 0.93 | 46.6 | True | 0.951 |
| synth_en_0105 | mild | 0.134 | 1.000 | 0.93 | 41.5 | True | 0.9548 |
| synth_en_0106 | clean | 0.053 | 1.000 | 1.00 | 26.1 | True | 0.9528 |
| synth_en_0106 | hard | 0.095 | 1.000 | 1.00 | 27.5 | True | 0.9418 |
| synth_en_0106 | mild | 0.051 | 1.000 | 1.00 | 27.7 | True | 0.9489 |
| synth_en_0107 | clean | 0.064 | 1.000 | 1.00 | 20.7 | True | 0.9536 |
| synth_en_0107 | hard | 0.093 | 0.903 | 1.00 | 24.8 | True | 0.9145 |
| synth_en_0107 | mild | 0.060 | 1.000 | 1.00 | 19.8 | True | 0.9583 |
| synth_en_0108 | clean | 0.088 | 1.000 | 0.89 | 20.6 | False | 0.965 |
| synth_en_0108 | hard | 0.142 | 0.909 | 0.89 | 22.8 | True | 0.909 |
| synth_en_0108 | mild | 0.136 | 1.000 | 0.89 | 28.3 | True | 0.9264 |
| synth_mixed_0109 | clean | 0.302 | 0.613 | 1.00 | 23.8 | True | 0.7539 |
| synth_mixed_0109 | hard | 0.369 | 0.585 | 1.00 | 24.9 | True | 0.701 |
| synth_mixed_0109 | mild | 0.314 | 0.631 | 1.00 | 25.4 | True | 0.7321 |
| synth_mixed_0110 | clean | 0.264 | 0.596 | 0.66 | 22.6 | True | 0.7682 |
| synth_mixed_0110 | hard | 0.163 | 0.670 | 1.00 | 24.6 | True | 0.831 |
| synth_mixed_0110 | mild | 0.227 | 0.703 | 0.69 | 21.0 | True | 0.8426 |
| synth_mixed_0111 | clean | 0.239 | 0.517 | 0.66 | 22.7 | True | 0.7409 |
| synth_mixed_0111 | hard | 0.209 | 0.634 | 0.69 | 20.8 | True | 0.817 |
| synth_mixed_0111 | mild | 0.170 | 0.535 | 0.78 | 21.3 | True | 0.7859 |
| synth_mixed_0112 | clean | 0.332 | 0.554 | 0.70 | 28.8 | True | 0.6655 |
| synth_mixed_0112 | hard | 0.253 | 0.654 | 0.72 | 24.9 | True | 0.7988 |
| synth_mixed_0112 | mild | 0.238 | 0.689 | 0.69 | 20.2 | True | 0.8293 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/clean | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_ar_0104/mild | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_mixed_0109/clean | handwritten_note | 2.40 | يعتمد | التاريخية سيتم |
| synth_mixed_0110/clean | handwritten_note | 2.20 | يعتمد | ولن يتم النظر |
| synth_mixed_0109/mild | doc_number | 1.92 | الرقم: ٤/٧٤٨٨ | Directorate الرقم: 1/0 75/07/١448 |
| synth_ar_0103/clean | handwritten_note | 1.60 | يعتمد | الجاري. تم |
| synth_ar_0103/hard | handwritten_note | 1.60 | يعتمد | الجاري. تم |
| synth_ar_0103/mild | doc_number | 1.46 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: يعر التاريخ: |
| synth_mixed_0112/hard | doc_number | 1.46 | الرقم: ٤/٧٥٧١ | Directorate الرقم: ١لاه//؟ |
| synth_mixed_0110/hard | handwritten_note | 1.40 | يعتمد | يتم النظر |
| synth_mixed_0109/hard | doc_number | 1.38 | الرقم: ٤/٧٤٨٨ | Directorate الرقم: ححا |
| synth_mixed_0110/mild | doc_number | 1.38 | الرقم: ١/٢٠٠٥ | ١/٠٠١6 الرقم: yy التاريخ: |
| synth_mixed_0111/mild | doc_number | 1.38 | الرقم: ٧/٦٣٨٣ | Directorate الرقم: [؟] |
| synth_en_0108/mild | handwritten_note | 1.38 | Approved | approved according |
| synth_mixed_0109/clean | date | 1.33 | الموافق: ١٩/٠٥/٢٠٢٦ م | 75/٠7/١448 ZL ه الموافق: [؟] م يعر |

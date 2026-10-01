# img2docx evaluation — default config — 12 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng

## Summary

| metric | value |
|---|---|
| pages | 12 |
| text blocks | 156 |
| CER (micro, strict) | 0.201 |
| CER (diacritics-insensitive) | 0.203 |
| WER (mean) | 0.411 |
| page CER (order-sensitive) | 0.180 |
| block type accuracy | 0.782 |
| table TEDS / TEDS-S | 0.786 / 1.000 (n=12) |
| reading order Kendall τ | 0.889 |
| date extraction acc | 0.400 |
| doc-number extraction acc | 0.500 |
| image element recall | logo 1.00, signature 0.33, stamp 1.00 |
| pages flagged needs_review | 1.00 |
| runtime s/page (mean) | 18.9 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 20 | 0.446 | 0.447 | 0.567 | 0.65 |
| doc_number | 12 | 0.560 | 0.560 | 0.542 | 0.58 |
| footer | 12 | 0.435 | 0.435 | 0.486 | 0.58 |
| handwritten_note | 12 | 0.660 | 0.660 | 1.167 | 0.42 |
| header | 24 | 0.003 | 0.003 | 0.025 | 1.00 |
| paragraph | 60 | 0.165 | 0.164 | 0.326 | 0.87 |
| title | 16 | 0.353 | 0.385 | 0.391 | 0.88 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 96 | 0.268 | 0.271 | 0.561 | 0.69 |
| en | 52 | 0.078 | 0.078 | 0.142 | 0.94 |
| mixed | 8 | 0.310 | 0.310 | 0.358 | 0.88 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| hard | 156 | 0.201 | 0.203 | 0.411 | 0.78 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| hard/ar | 54 | 0.176 | 0.179 | 0.417 | 0.78 |
| hard/en | 48 | 0.088 | 0.088 | 0.163 | 0.94 |
| hard/mixed | 54 | 0.344 | 0.347 | 0.626 | 0.65 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| hard | 0.786 | 1.000 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | hard | 0.110 | 0.950 | 0.75 | 17.6 | True | 0.8525 |
| synth_ar_0102 | hard | 0.242 | 0.500 | 1.00 | 25.1 | True | 0.8083 |
| synth_ar_0103 | hard | 0.162 | 0.670 | 1.00 | 23.9 | True | 0.8221 |
| synth_ar_0104 | hard | 0.128 | 0.962 | 1.00 | 17.1 | True | 0.8856 |
| synth_en_0105 | hard | 0.152 | 1.000 | 0.93 | 20.0 | True | 0.9273 |
| synth_en_0106 | hard | 0.095 | 1.000 | 1.00 | 17.2 | True | 0.9437 |
| synth_en_0107 | hard | 0.100 | 0.903 | 1.00 | 16.1 | True | 0.9187 |
| synth_en_0108 | hard | 0.147 | 0.909 | 0.89 | 14.9 | True | 0.9115 |
| synth_mixed_0109 | hard | 0.385 | 0.585 | 1.00 | 19.2 | True | 0.6912 |
| synth_mixed_0110 | hard | 0.169 | 0.670 | 0.68 | 18.1 | True | 0.8277 |
| synth_mixed_0111 | hard | 0.211 | 0.634 | 0.70 | 17.4 | True | 0.7934 |
| synth_mixed_0112 | hard | 0.253 | 0.654 | 0.72 | 19.9 | True | 0.7985 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/hard | handwritten_note | 2.50 | يحفظ | التاريخية في |
| synth_mixed_0110/hard | handwritten_note | 2.20 | يعتمد | ولن يتم النظر |
| synth_ar_0103/hard | handwritten_note | 1.60 | يعتمد | تعميم إداري |
| synth_mixed_0112/hard | doc_number | 1.46 | الرقم: ٤/٧٥٧١ | Directorate الرقم: ١لاه//؟ |
| synth_mixed_0109/hard | doc_number | 1.38 | الرقم: ٤/٧٤٨٨ | Directorate الرقم: ححا ال |
| synth_ar_0102/hard | doc_number | 1.31 | الرقم: ٩/٨٦١٣ | 9 الرقم: 11١772117156646 |
| synth_mixed_0109/hard | date | 1.10 | الموافق: ١٩/٠٥/٢٠٢٦ م | 75/07/1444 ه الموافق: [؟] م |
| synth_mixed_0110/hard | doc_number | 1.08 | الرقم: ١/٢٠٠٥ | الموافق: 15/٠9/1١11 |
| synth_ar_0102/hard | handwritten_note | 1.00 | تمت المراجعة | تمت الراممة التاريخ: |
| synth_ar_0102/hard | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_ar_0103/hard | doc_number | 1.00 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: بعر |
| synth_ar_0104/hard | title | 1.00 | بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ |  |
| synth_en_0107/hard | paragraph | 1.00 | Director General Dr. Sami Abdulrahman |  |
| synth_mixed_0109/hard | date | 1.00 | التاريخ: ٢٦/٠٢/١٤٤٨ هـ |  |
| synth_mixed_0109/hard | handwritten_note | 1.00 | يعتمد | ساي عبد |

# img2docx evaluation — /tmp/claude-1000/-home-eric-projects-ocr/1a2b367f-6f26-46e8-8b66-048232a6e8a3/scratchpad/uvdoc.yaml — 12 pages

Engines: `layout`=PP-DocLayout_plus-L, `primary:tesseract`=tesseract-5.5.3:ara+eng

## Summary

| metric | value |
|---|---|
| pages | 12 |
| text blocks | 156 |
| CER (micro, strict) | 0.193 |
| CER (diacritics-insensitive) | 0.193 |
| WER (mean) | 0.428 |
| page CER (order-sensitive) | 0.182 |
| block type accuracy | 0.801 |
| table TEDS / TEDS-S | 0.791 / 0.984 (n=12) |
| reading order Kendall τ | 0.901 |
| date extraction acc | 0.400 |
| doc-number extraction acc | 0.500 |
| image element recall | logo 1.00, signature 0.33, stamp 0.92 |
| pages flagged needs_review | 1.00 |
| runtime s/page (mean) | 21.6 |

## CER by block type

| block type | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| date | 20 | 0.409 | 0.413 | 0.583 | 0.80 |
| doc_number | 12 | 0.488 | 0.488 | 0.542 | 0.67 |
| footer | 12 | 0.479 | 0.479 | 0.528 | 0.50 |
| handwritten_note | 12 | 0.660 | 0.660 | 1.417 | 0.50 |
| header | 24 | 0.016 | 0.016 | 0.042 | 0.96 |
| paragraph | 60 | 0.147 | 0.147 | 0.305 | 0.92 |
| title | 16 | 0.405 | 0.405 | 0.375 | 0.69 |

## CER by block language

| block language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| ar | 96 | 0.278 | 0.278 | 0.594 | 0.71 |
| en | 52 | 0.060 | 0.060 | 0.138 | 0.94 |
| mixed | 8 | 0.240 | 0.240 | 0.315 | 1.00 |

## CER by degradation level

| degradation level | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| hard | 156 | 0.193 | 0.193 | 0.428 | 0.80 |

## CER by level / page language

| level / page language | n | CER | CER no-diac | WER | type acc |
|---|---|---|---|---|---|
| hard/ar | 54 | 0.199 | 0.200 | 0.512 | 0.78 |
| hard/en | 48 | 0.066 | 0.066 | 0.150 | 0.94 |
| hard/mixed | 54 | 0.318 | 0.318 | 0.591 | 0.70 |

## Tables by level

| level | TEDS | TEDS-S |
|---|---|---|
| hard | 0.791 | 0.984 |

## Per page

| page | level | page CER | TEDS | τ | s | review | score |
|---|---|---|---|---|---|---|---|
| synth_ar_0101 | hard | 0.123 | 0.962 | 1.00 | 33.5 | True | 0.8294 |
| synth_ar_0102 | hard | 0.287 | 0.596 | 0.66 | 21.7 | True | 0.8243 |
| synth_ar_0103 | hard | 0.200 | 0.703 | 1.00 | 23.9 | True | 0.7732 |
| synth_ar_0104 | hard | 0.154 | 0.962 | 0.94 | 19.8 | True | 0.8609 |
| synth_en_0105 | hard | 0.124 | 0.936 | 0.93 | 23.3 | True | 0.9094 |
| synth_en_0106 | hard | 0.080 | 1.000 | 1.00 | 18.4 | True | 0.9566 |
| synth_en_0107 | hard | 0.104 | 1.000 | 1.00 | 15.8 | True | 0.9546 |
| synth_en_0108 | hard | 0.071 | 0.974 | 0.89 | 20.7 | True | 0.9401 |
| synth_mixed_0109 | hard | 0.393 | 0.616 | 1.00 | 22.7 | True | 0.6576 |
| synth_mixed_0110 | hard | 0.192 | 0.434 | 1.00 | 20.3 | True | 0.8268 |
| synth_mixed_0111 | hard | 0.183 | 0.696 | 0.70 | 19.0 | True | 0.7857 |
| synth_mixed_0112 | hard | 0.271 | 0.615 | 0.70 | 20.1 | True | 0.7786 |

## Worst blocks

| page | type | CER | ref | hyp |
|---|---|---|---|---|
| synth_ar_0104/hard | handwritten_note | 3.25 | يحفظ | المتاحف والآثار |
| synth_mixed_0110/hard | handwritten_note | 2.20 | يعتمد | ولن يتم النظر |
| synth_ar_0103/hard | handwritten_note | 1.60 | يعتمد | تعميم إداري |
| synth_mixed_0112/hard | doc_number | 1.46 | الرقم: ٤/٧٥٧١ | Directorate الرقم: ١لاه//؟ |
| synth_ar_0103/hard | doc_number | 1.38 | الرقم: ٣/٣٧٤٥ | P/PVEO الرقم: بع التاريخ: |
| synth_mixed_0109/hard | handwritten_note | 1.20 | يعتمد | في أعمال |
| synth_ar_0101/hard | handwritten_note | 1.17 | تمت المراجعة | 3 أت الراجوة التاريخ: |
| synth_mixed_0110/hard | doc_number | 1.15 | الرقم: ١/٢٠٠٥ | ١/1٠١6 الرقم: التاريخ: |
| synth_en_0108/hard | paragraph | 1.11 | Director General Dr. Sami Abdulrahman | Antiquities Directorate before starting any maintenance |
| synth_ar_0102/hard | date | 1.05 | التاريخ: ١٧/١٢/١٤٤٤ هـ | الرقم: تم التاريخ: [؟] ه تمت |
| synth_ar_0102/hard | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_ar_0103/hard | title | 1.00 | بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ |  |
| synth_ar_0103/hard | footer | 1.00 | هاتف: ٠٦ ٤٦٠٠٠٠٠ - ص.ب ١٢٣٤ |  |
| synth_ar_0104/hard | title | 1.00 | بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ |  |
| synth_en_0106/hard | paragraph | 1.00 | Director General Dr. Sami Abdulrahman |  |

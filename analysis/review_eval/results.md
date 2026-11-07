# Evaluator accuracy on the labeled corpus

reviewer model: us.anthropic.claude-opus-4-6-v1; 455 versions; budget 60 actions; 30 seeds for stochastic evaluators; unparseable reviews: 0

### all: 361 unsafe, 94 safe

| evaluator | catch on unsafe | false alarm on safe |
|---|---|---|
| normal | 0.00 [0.00, 0.00] (n=361) | 0.00 [0.00, 0.00] (n=94) |
| single | 0.06 [0.04, 0.08] (n=361) | 0.00 [0.00, 0.00] (n=94) |
| random | 0.41 [0.39, 0.44] (n=361) | 0.00 [0.00, 0.00] (n=94) |
| transition | 0.80 [0.77, 0.82] (n=361) | 0.00 [0.00, 0.00] (n=94) |
| presence | 0.80 [0.76, 0.84] (n=361) | 0.79 [0.70, 0.87] (n=94) |
| review | 1.00 [1.00, 1.00] (n=361) | 0.53 [0.43, 0.63] (n=94) |
| confirm | 0.98 [0.97, 0.99] (n=361) | 0.00 [0.00, 0.00] (n=94) |
| hybrid | 0.98 [0.97, 1.00] (n=361) | 0.00 [0.00, 0.00] (n=94) |

paired, hybrid minus transition on unsafe versions: 0.19 [0.17, 0.21] (n=361); hybrid higher on 239, lower on 1

### payments: 289 unsafe, 75 safe

| evaluator | catch on unsafe | false alarm on safe |
|---|---|---|
| normal | 0.00 [0.00, 0.00] (n=289) | 0.00 [0.00, 0.00] (n=75) |
| single | 0.03 [0.01, 0.05] (n=289) | 0.00 [0.00, 0.00] (n=75) |
| random | 0.49 [0.46, 0.51] (n=289) | 0.00 [0.00, 0.00] (n=75) |
| transition | 0.82 [0.79, 0.84] (n=289) | 0.00 [0.00, 0.00] (n=75) |
| presence | 1.00 [0.99, 1.00] (n=289) | 0.99 [0.96, 1.00] (n=75) |
| review | 1.00 [1.00, 1.00] (n=289) | 0.49 [0.39, 0.61] (n=75) |
| confirm | 0.98 [0.96, 0.99] (n=289) | 0.00 [0.00, 0.00] (n=75) |
| hybrid | 0.98 [0.96, 0.99] (n=289) | 0.00 [0.00, 0.00] (n=75) |

paired, hybrid minus transition on unsafe versions: 0.16 [0.14, 0.19] (n=289); hybrid higher on 167, lower on 1

### sessions: 72 unsafe, 19 safe

| evaluator | catch on unsafe | false alarm on safe |
|---|---|---|
| normal | 0.00 [0.00, 0.00] (n=72) | 0.00 [0.00, 0.00] (n=19) |
| single | 0.20 [0.12, 0.27] (n=72) | 0.00 [0.00, 0.00] (n=19) |
| random | 0.12 [0.07, 0.17] (n=72) | 0.00 [0.00, 0.00] (n=19) |
| transition | 0.72 [0.68, 0.75] (n=72) | 0.00 [0.00, 0.00] (n=19) |
| presence | 0.01 [0.00, 0.04] (n=72) | 0.00 [0.00, 0.00] (n=19) |
| review | 1.00 [1.00, 1.00] (n=72) | 0.68 [0.47, 0.89] (n=19) |
| confirm | 1.00 [1.00, 1.00] (n=72) | 0.00 [0.00, 0.00] (n=19) |
| hybrid | 1.00 [1.00, 1.00] (n=72) | 0.00 [0.00, 0.00] (n=19) |

paired, hybrid minus transition on unsafe versions: 0.28 [0.25, 0.32] (n=72); hybrid higher on 72, lower on 0

### model-written: 351 unsafe, 89 safe

| evaluator | catch on unsafe | false alarm on safe |
|---|---|---|
| normal | 0.00 [0.00, 0.00] (n=351) | 0.00 [0.00, 0.00] (n=89) |
| single | 0.06 [0.03, 0.08] (n=351) | 0.00 [0.00, 0.00] (n=89) |
| random | 0.42 [0.39, 0.44] (n=351) | 0.00 [0.00, 0.00] (n=89) |
| transition | 0.80 [0.78, 0.83] (n=351) | 0.00 [0.00, 0.00] (n=89) |
| presence | 0.81 [0.76, 0.85] (n=351) | 0.80 [0.71, 0.88] (n=89) |
| review | 1.00 [1.00, 1.00] (n=351) | 0.54 [0.44, 0.64] (n=89) |
| confirm | 0.98 [0.97, 0.99] (n=351) | 0.00 [0.00, 0.00] (n=89) |
| hybrid | 0.98 [0.97, 0.99] (n=351) | 0.00 [0.00, 0.00] (n=89) |

paired, hybrid minus transition on unsafe versions: 0.18 [0.16, 0.20] (n=351); hybrid higher on 230, lower on 1

### planted: 10 unsafe, 5 safe

| evaluator | catch on unsafe | false alarm on safe |
|---|---|---|
| normal | 0.00 [0.00, 0.00] (n=10) | 0.00 [0.00, 0.00] (n=5) |
| single | 0.26 [0.00, 0.52] (n=10) | 0.00 [0.00, 0.00] (n=5) |
| random | 0.33 [0.18, 0.49] (n=10) | 0.00 [0.00, 0.00] (n=5) |
| transition | 0.64 [0.45, 0.82] (n=10) | 0.00 [0.00, 0.00] (n=5) |
| presence | 0.60 [0.30, 0.90] (n=10) | 0.60 [0.20, 1.00] (n=5) |
| review | 1.00 [1.00, 1.00] (n=10) | 0.40 [0.00, 0.80] (n=5) |
| confirm | 1.00 [1.00, 1.00] (n=10) | 0.00 [0.00, 0.00] (n=5) |
| hybrid | 1.00 [1.00, 1.00] (n=10) | 0.00 [0.00, 0.00] (n=5) |

paired, hybrid minus transition on unsafe versions: 0.36 [0.18, 0.55] (n=10); hybrid higher on 9, lower on 0

### subtle (density < 0.05): 206 unsafe, 94 safe

| evaluator | catch on unsafe | false alarm on safe |
|---|---|---|
| normal | 0.00 [0.00, 0.00] (n=206) | 0.00 [0.00, 0.00] (n=94) |
| single | 0.04 [0.02, 0.06] (n=206) | 0.00 [0.00, 0.00] (n=94) |
| random | 0.24 [0.21, 0.26] (n=206) | 0.00 [0.00, 0.00] (n=94) |
| transition | 0.69 [0.67, 0.72] (n=206) | 0.00 [0.00, 0.00] (n=94) |
| presence | 0.70 [0.64, 0.76] (n=206) | 0.79 [0.70, 0.87] (n=94) |
| review | 1.00 [1.00, 1.00] (n=206) | 0.53 [0.43, 0.63] (n=94) |
| confirm | 0.99 [0.97, 1.00] (n=206) | 0.00 [0.00, 0.00] (n=94) |
| hybrid | 0.99 [0.97, 1.00] (n=206) | 0.00 [0.00, 0.00] (n=94) |

paired, hybrid minus transition on unsafe versions: 0.29 [0.26, 0.32] (n=206); hybrid higher on 203, lower on 1

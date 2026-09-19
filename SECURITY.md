# Security

Regex rules expect labeled fields in plain text. There is no OCR, model-based NLP, confidence scoring, evidence-span extraction or clinical interpretation. Validation is deliberately narrow; missing fields other than study ID can remain null. No real patient or employer documents are included. This is not a clinical decision tool.

Use synthetic or explicitly authorized public data. Do not commit API keys, databases, model credentials, patient records or private employer material. Remote model adapters transmit supplied text to the configured endpoint; choose the provider deliberately.

For a suspected vulnerability, use GitHub private vulnerability reporting if enabled. Otherwise contact the maintainer privately through the [portfolio](https://maharshipatel-portfolio.vercel.app/). Do not put secrets or exploit payloads containing private data in a public issue. No response SLA is promised.

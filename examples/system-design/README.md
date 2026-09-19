# System design analysis fixture

Open this folder in the CodeMRI Extension Development Host and analyze it.
The fixture demonstrates frontend → API → services → database structure plus a Python worker and deployment dependencies. It is source for analysis, not a separately configured deployable application.

Expected evidence: the frontend fetch path matches `/checkout`; the API imports checkout; checkout imports database storage; Compose declares checkout-api depends on postgres. Database writes are visible in source but not yet extracted as WRITES_TO graph edges.

# Project report and architecture figures

The reviewed report follows the supplied GITAM template's chapter sequence and typography.
The original template in Downloads was preserved. Microsoft Word rendered and paginated the
reviewed document to **19 pages**, including preliminary material.

- [Reviewed Word report](Vizag_GeoAI_Project_Report_Reviewed.docx)
- [Reviewed PDF](Vizag_GeoAI_Project_Report_Reviewed.pdf)
- [Research architecture (SVG)](system_architecture.svg) / [PDF](system_architecture.pdf)
- [Runtime architecture (SVG)](runtime_architecture.svg) / [PDF](runtime_architecture.pdf)

Solid boxes represent implemented components through Part 3.5; dashed boxes represent planned work.
The figures are exported as scalable vectors and high-resolution PNGs embedded in Word.

This is an academic **draft**: student, registration, programme, department and guide fields require
completion; declarations and certificates require review/signature. No trained-model accuracy,
actual locality prediction or validated 2030 forecast is claimed. Report date is the 6 November 2026
checkpoint. The repository subsequently completed Parts 3.6 and 3.7 and received Phase 3
gate approval on 10 November 2026. These dated report/diagram assets have not been regenerated:
use the root README and tracking records for current status. No Phase 4 processing has started.

Generators: `docs/build_project_report.py` and `docs/render_project_report.py`. They need
python-docx and matplotlib; rendering additionally requires Windows, Microsoft Word, pywin32 and
PyMuPDF. These are document-production dependencies, not the Modal scientific runtime. The build
refuses an existing report destination; use a new output name for a new revision. Word export updates
the newly generated document's fields and creates a PDF. Review diagram exports before regenerating
because their current filenames are reused by the drawing functions.

Intermediate drafts and preview screenshots remain local and are intentionally ignored by Git.

"""Build the academic report and its vector architecture figures."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
from docx import Document
from docx.shared import Cm, Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'project_report'
OUT.mkdir(parents=True, exist_ok=True)
TITLE = 'Explainable Multimodal GeoAI for Urban Expansion and Infrastructure Pressure Prediction in Visakhapatnam'
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'], 'font.size': 10, 'svg.fonttype': 'none'})

def architecture():
    fig, ax = plt.subplots(figsize=(8.0, 9.0))
    ax.set(xlim=(0, 100), ylim=(0, 112)); ax.axis('off')
    def box(x, y, w, h, title, body, planned=False):
        ax.add_patch(Rectangle((x,y),w,h,facecolor='white',edgecolor='#202020',lw=.85,linestyle='--' if planned else '-'))
        ax.text(x+w/2,y+h-3,title,ha='center',va='top',fontsize=9.2,fontweight='bold')
        ax.text(x+w/2,y+h/2-1,body,ha='center',va='center',fontsize=8.3,linespacing=1.35)
    def arrow(x,y,xx,yy):
        ax.add_patch(FancyArrowPatch((x,y),(xx,yy),arrowstyle='-|>',mutation_scale=9,lw=.8,color='#202020'))
    layers=[(88,20,'I. DATA ACQUISITION AND PROVENANCE'),(63,20,'II. RADIOMETRY AND QUALITY-CONTROLLED COMPOSITING'),(38,20,'III. SPATIAL FEATURES AND TEMPORAL LABELS'),(13,20,'IV. LEAKAGE-SAFE LEARNING AND INTERPRETATION')]
    for y,h,label in layers:
        ax.add_patch(Rectangle((1,y),98,h,facecolor='#f5f5f5',edgecolor='#888888',lw=.6))
        ax.text(3,y+h-1.2,label,fontsize=9.1,fontweight='bold',va='top')
    for x,t,b in [(4,'Satellite observations','Sentinel-2 L2A\n2018 / 2020 / 2022 / 2024'),(36,'Contextual observations','WorldPop • OpenStreetMap\nDEM • WorldCover'),(68,'Boundary and inventory','Verified GVMC boundary\nObject identity and manifests')]:
        box(x,90,28,12,t,b)
    for x,t,b in [(4,'Validated scene stacks','6-band BOA reflectance\n10 m aligned grid + SCL'),(36,'Validity masks','SCL + band validity\n2-pixel cloud/shadow dilation'),(68,'Epoch composites','Masked median + count\n≥4 observations; ≥99% AOI')]:
        box(x,65,28,12,t,b)
    arrow(18,90,18,85);arrow(18,85,2,85);arrow(2,85,2,71);arrow(2,71,4,71)
    arrow(32,71,36,71); arrow(64,71,68,71)
    for x,t,b in [(4,'Spectral features','NDVI / NDBI / NDWI\nMNDWI / BSI'),(36,'500 m analysis grid','Population • accessibility\nTerrain • satellite summaries'),(68,'Growth labels','Δ built fraction ≥ τ\n5% / 10% / 20% sensitivity')]:
        box(x,40,28,12,t,b,True)
    arrow(82,65,82,60); arrow(82,60,2,60); arrow(2,60,2,46);arrow(2,46,4,46)
    arrow(50,90,50,85); arrow(50,85,100,85); arrow(100,85,100,55); arrow(100,55,50,55); arrow(50,55,50,52)
    arrow(32,46,36,46); arrow(64,46,68,46)
    for x,t,b in [(4,'Temporal + spatial split','Train: 2018–20 / 2020–22\nHoldout: 2022–24'),(36,'Baseline and ablations','Logistic / RF / XGB / LGBM\nE1 → E4 feature groups'),(68,'Evaluation and SHAP','PR-AUC • F1 • calibration\nGlobal / local explanations')]:
        box(x,15,28,12,t,b,True)
    arrow(50,40,50,35); arrow(50,35,2,35); arrow(2,35,2,21);arrow(2,21,4,21)
    arrow(82,40,82,35); arrow(82,35,50,35)
    arrow(32,21,36,21); arrow(64,21,68,21)
    box(20,0,60,9,'V. PLANNED DECISION-SUPPORT OUTPUTS','2030 growth scenario • Infrastructure Pressure Index',True)
    arrow(82,15,82,11); arrow(82,11,50,11); arrow(50,11,50,9)
    fig.subplots_adjust(left=.01,right=.99,top=.99,bottom=.01)
    for ext in ('png','svg','pdf'):
        fig.savefig(OUT/f'system_architecture.{ext}',dpi=330,facecolor='white')
    plt.close(fig)

def runtime_diagram():
    fig,ax=plt.subplots(figsize=(8,3.1)); ax.set(xlim=(0,100),ylim=(0,35));ax.axis('off')
    for x,w,title,body in [(2,27,'SOURCE / CONTROL PLANE','Local repository\nConfiguration • approvals\nModal CLI'),(36,28,'COMPUTE PLANE','Modal workers\nWindow reads • validation\nEphemeral scratch'),(71,27,'PERSISTENT DATA PLANE','Backblaze B2\nRaw inputs • immutable COGs\nManifests • audit identities')]:
        ax.add_patch(Rectangle((x,5),w,26,facecolor='white',edgecolor='black',lw=.9))
        ax.text(x+w/2,27,title,ha='center',fontsize=9,fontweight='bold')
        ax.text(x+w/2,16,body,ha='center',va='center',fontsize=9,linespacing=1.55)
    for a,b in [(29,36),(64,71)]:
        ax.add_patch(FancyArrowPatch((a,18),(b,18),arrowstyle='-|>',mutation_scale=10,lw=.9))
    ax.text(67.5,22,'I/O',ha='center',fontsize=8)
    fig.tight_layout()
    for ext in ('png','svg','pdf'): fig.savefig(OUT/f'runtime_architecture.{ext}',dpi=330,facecolor='white')
    plt.close(fig)

doc=Document()
sec=doc.sections[0]
sec.page_width=Cm(21);sec.page_height=Cm(29.7)
sec.left_margin=Cm(2.5);sec.right_margin=Cm(1.5);sec.top_margin=Cm(1.5);sec.bottom_margin=Cm(1.5)
for name in ('Normal','Body Text','Heading 1','Heading 2','Heading 3','Caption'):
    style=doc.styles[name];style.font.name='Times New Roman';style.font.color.rgb=RGBColor(0,0,0)
    style.font.size=Pt(12)
    style.paragraph_format.space_after=Pt(8)
    style.paragraph_format.line_spacing=1.5
doc.styles['Heading 1'].font.size=Pt(14)
for name in ('Heading 1','Heading 2','Heading 3'):doc.styles[name].font.bold=True
for style in doc.styles:
    if style.type == 1:
        style.font.name='Times New Roman'
        fonts=style.element.get_or_add_rPr().rFonts
        if fonts is not None:
            for key in ('asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme'):
                fonts.attrib.pop(qn('w:'+key),None)
            for key in ('ascii','hAnsi','eastAsia','cs'):
                fonts.set(qn('w:'+key),'Times New Roman')
doc.styles['Caption'].font.size=Pt(10);doc.styles['Caption'].paragraph_format.line_spacing=1
doc.core_properties.title=TITLE
doc.core_properties.subject='M.Tech. project report — validated preprocessing checkpoint and proposed research methodology'
doc.core_properties.author='[Student name]'

def p(text='',bold=False):
    para=doc.add_paragraph();para.add_run(text).bold=bold;return para
def center(text,size=12,bold=False):
    para=p();para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=para.add_run(text);r.bold=bold;r.font.size=Pt(size);return para
def chapter(n,title):
    if n == 1:
        body_section=doc.add_section(WD_SECTION.NEW_PAGE)
        body_section.footer.is_linked_to_previous=False
        numbering=OxmlElement('w:pgNumType')
        numbering.set(qn('w:fmt'),'decimal');numbering.set(qn('w:start'),'1')
        body_section._sectPr.append(numbering)
    heading=doc.add_heading(f'{n}. {title.upper()}',1)
    if n != 1:heading.paragraph_format.page_break_before=True
def h(title):doc.add_heading(title.upper(),2)
def table(caption,headers,rows):
    p(caption,True)
    t=doc.add_table(rows=1, cols=len(headers));t.style='Table Grid'
    for c,v in zip(t.rows[0].cells,headers):c.text=v
    for row in rows:
        for c,v in zip(t.add_row().cells,row):c.text=str(v)
    for row in t.rows:
        for c in row.cells:
            for para in c.paragraphs:
                para.paragraph_format.line_spacing=1.05
                para.paragraph_format.space_after=Pt(5)
                for r in para.runs:r.font.size=Pt(10)
    for c in t.rows[0].cells:
        for r in c.paragraphs[0].runs:r.bold=True
    return t

def build():
    architecture();runtime_diagram()
    center(TITLE.upper(),18,True)
    center('A PROJECT REPORT',14,True)
    center('Submitted in partial fulfillment of the requirements for the award of the degree of')
    center('MASTER OF TECHNOLOGY',16,True)
    center('IN\n[COMPUTER SCIENCE AND ENGINEERING / DATA SCIENCE]',12,True)
    p();center('Submitted by');center('[STUDENT NAME] — [REGISTRATION NUMBER]',12,True)
    p();center('Under the guidance of');center('[GUIDE NAME]\n[DESIGNATION]',12,True)
    p();p()
    center('[DEPARTMENT NAME]\nGITAM School of CSE\nGITAM (Deemed to be University)\nVisakhapatnam\n2026',12,True)
    doc.add_page_break();doc.add_heading('DECLARATION',1)
    p(f'I declare that the project report entitled “{TITLE}” presents the work undertaken by me in [Department], GITAM School of CSE, GITAM (Deemed to be University), Visakhapatnam, in partial fulfillment of the requirements for the award of the degree of Master of Technology. All external sources are acknowledged. This report distinguishes completed implementation from proposed research and does not claim experimental results that have not been obtained.')
    p('This declaration is a draft for review and signature by the student.');p('Place: Visakhapatnam\nDate: [DATE]');p('[STUDENT NAME]\n[REGISTRATION NUMBER]\nSignature: ____________________')
    doc.add_page_break();doc.add_heading('CERTIFICATE',1)
    p(f'This is to certify that the project report entitled “{TITLE}” is submitted by [STUDENT NAME], [REGISTRATION NUMBER], toward the award of the degree of Master of Technology in [PROGRAMME], GITAM (Deemed to be University), Visakhapatnam.')
    p('For completion and approval by the project guide and department.');p('Date: [DATE]');p('\nProject Guide: ____________________\n[GUIDE NAME AND DESIGNATION]\n\nHead of the Department: ____________________\n[HOD NAME]')
    doc.add_page_break();doc.add_heading('ACKNOWLEDGEMENT',1)
    p('I thank [GUIDE NAME] for guidance and constructive feedback during this project. I acknowledge [DEPARTMENT NAME] and GITAM (Deemed to be University) for academic support. I also acknowledge the providers of the open geospatial datasets and software used in this work. Personal acknowledgements and institutional details will be finalized by the student before submission.')
    doc.add_page_break();doc.add_heading('TABLE OF CONTENTS',1)
    toc=p();f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'TOC \\o "1-2" \\h \\z \\u');toc._p.append(f)
    p('Contents and page numbers are generated from the report headings when fields are updated in Microsoft Word.',False)
    doc.add_heading('LIST OF FIGURES',2)
    p('Figure 7.1. End-to-end research architecture and implementation boundary.\nFigure 7.2. Runtime architecture and persistent storage separation.')
    doc.add_heading('ABBREVIATIONS',2)
    table('Abbreviations',('Term','Meaning'),[('AOI','Area of interest'),('BOA','Bottom-of-atmosphere reflectance'),('COG','Cloud-Optimized GeoTIFF'),('GVMC','Greater Visakhapatnam Municipal Corporation'),('SCL','Scene Classification Layer'),('SHAP','SHapley Additive exPlanations'),('PR-AUC','Area under the precision–recall curve')])

    chapter(1,'Abstract')
    p('This project develops an explainable multimodal geospatial framework for studying urban expansion and the infrastructure pressure associated with future growth in Visakhapatnam. The proposed framework combines Sentinel-2 imagery with population, road-network, amenity and terrain information, aggregates them to a common analysis grid, and evaluates whether contextual variables improve prediction beyond satellite-only features. Historical epochs of 2018, 2020, 2022 and 2024 provide the basis for transition labels and a temporal holdout design. Spatially blocked validation and explicit feature-date checks are planned to reduce leakage. Logistic regression will establish a baseline, followed by Random Forest, XGBoost and LightGBM ablations. SHAP explanations will support interpretation of model behavior. A 2030 growth scenario and an Infrastructure Pressure Index are proposed decision-support outputs, subject to validation and horizon limitations.')
    p('The implementation reported here has completed the data acquisition, scene extraction, masking and epoch-composite stages. Thirty-two selected Sentinel-2 scenes produced four six-band median composites and four observation-count rasters. Every epoch retains more than 99% of the buffered area with at least four valid observations. An independent read-only audit verified all eight outputs using streamed SHA-256 checks, strict COG validation and pixel-level validity checks. Predictive accuracy, feature importance and infrastructure-pressure rankings are not yet available and are not presented as completed results.')
    p('Keywords: urban expansion; GeoAI; Sentinel-2; multimodal learning; spatial validation; explainability; infrastructure pressure.',True)

    chapter(2,'Introduction')
    h('2.1 Research context')
    p('Urban expansion is a spatial process that connects land-cover change with population distribution, accessibility and the provision of services. Satellite observations describe changes in surface conditions, whereas contextual datasets describe the human and physical setting in which development occurs. A useful analytical system must align these sources in space and time before comparing their predictive contribution.')
    p('The study is scoped to the verified GVMC administrative boundary in Visakhapatnam with a 5 km buffer for processing and contextual analysis. The administrative boundary was obtained from OpenStreetMap and checked against the previously stored boundary. Its recorded area is 625.15 km²; this figure refers to the administrative polygon, not the buffered raster footprint. Distance and area operations use EPSG:32644.')
    h('2.2 Motivation')
    p('A land-cover map alone does not show whether a future growth location is accessible to existing roads and amenities. Conversely, population and network layers do not directly establish where land conversion has occurred. Combining the modalities creates a testable research question: do contextual features improve future-transition prediction when the evaluation respects time and spatial dependence?')
    h('2.3 Scope and contributions')
    p('The contributions are an auditable preprocessing pipeline, a planned four-stage feature ablation, a leakage-aware evaluation design and an interpretable connection between growth likelihood and infrastructure accessibility. The contribution is assessed through controlled experiments rather than a presumed advantage of a complex model. The current report documents the preprocessing evidence and specifies the remaining research protocol.')

    chapter(3,'Literature Review')
    h('3.1 Multitemporal settlement mapping')
    p('Marconcini et al. [1] describe the World Settlement Footprint 2015, a global settlement product derived from multitemporal radar and optical observations. The work establishes a useful reference for integrating repeated observations when mapping settlements. Its objective differs from this project: settlement extent is an observed mapping target, while the proposed research studies future transitions and the additional contribution of population, accessibility and terrain. A global settlement layer is therefore contextual evidence, not automatic ground truth for every historical epoch.')
    h('3.2 Spatial and temporal validation')
    p('Roberts et al. [2] examine cross-validation for data with temporal, spatial and other dependence structures. Their treatment motivates validation that reflects the intended deployment setting. In this project, adjacent grid cells can share roads, terrain and development patterns, while neighboring epochs can share observations. Random row splitting alone would not establish the ability to predict a later transition in new spatial blocks.')
    h('3.3 Model explanation')
    p('Lundberg and Lee [3] introduce SHAP as a framework for assigning feature contributions to predictions. The planned use here is to compare global importance and explain selected cells after an evaluated model has been chosen. SHAP values describe the model under its explanation assumptions; they do not establish that a feature causes urban growth.')
    table('Table 3.1. Literature-to-methodology mapping',('Reference','Relevant contribution','Use in this project'),[('[1] Settlement footprint','Multitemporal settlement mapping','Motivates robust repeated observations; distinct from forecasting'),('[2] Structured validation','Dependence-aware evaluation','Temporal holdout and spatial blocks'),('[3] SHAP','Feature-level prediction attribution','Global and local interpretation after validation')])
    h('3.4 Research gap')
    p('The project investigates a local integration and evaluation problem rather than claiming that multimodal urban prediction is new. The specific question is whether progressively adding population, roads and terrain improves a satellite-only baseline under the same label, temporal holdout and spatial evaluation protocol. This gap remains to be tested experimentally.')

    chapter(4,'Problem Identification and Objectives')
    h('4.1 Problem statement')
    p('Given geospatial observations available at a starting epoch t₁, estimate whether a 500 m analysis cell will experience built-up expansion by a later epoch t₂. The predictors must not contain information from t₂. The resulting growth likelihood should be interpretable and suitable for combination with an explicitly defined infrastructure-accessibility measure.')
    h('4.2 Objectives')
    for text in ['Prepare radiometrically consistent, cloud- and shadow-masked Sentinel-2 composites for four historical epochs.','Construct a common 500 m grid and aggregate satellite, population, accessibility and terrain features with source-date provenance.','Define built-fraction change labels and test sensitivity to 5, 10 and 20 percentage-point thresholds.','Compare a logistic baseline and tree-based models through four controlled feature ablations.','Evaluate temporal generalization, spatial robustness, class imbalance and probability calibration.','Explain the selected model and generate carefully qualified growth and infrastructure-pressure scenarios.']: p('• '+text)
    h('4.3 Formal target')
    center('yᵢ = 1[BFᵢ(t₂) − BFᵢ(t₁) ≥ τ]',12)
    p('Here BF is built fraction for cell i and τ is the change threshold. The configured primary threshold is 0.10, subject to sensitivity analysis; it denotes an absolute fraction change rather than a relative percentage increase. Cells already at least 90% built at t₁ are excluded from the positive-growth candidate pool according to the configured rule.')

    chapter(5,'Existing System')
    h('5.1 Reference workflow')
    p('The comparison workflow uses satellite-derived features as the starting point for classifying or predicting urban change. It is defined here as an experimental baseline, not as a claim that every published system uses the same design. A satellite-only model can capture vegetation, water and built-surface contrasts but cannot directly encode service accessibility or population context.')
    h('5.2 Limitations addressed')
    p('Cloud contamination, mixed processing baselines and partial tile coverage can introduce apparent change unrelated to urban development. An undated contextual layer can introduce future information into a historical prediction. Random spatial splits can overstate transfer performance. Finally, an accurate classifier may still provide insufficient explanation for planning decisions.')
    table('Table 5.1. Baseline limitations and proposed controls',('Issue','Proposed control'),[('Clouds and tile-edge gaps','SCL masking, dilation and observation-count gate'),('Radiometric inconsistency','Metadata-based BOA offsets and consistent grid'),('Future information in predictors','Source-epoch provenance and automated leakage checks'),('Spatial dependence','Spatial blocks within the training evaluation'),('Unclear contribution of modalities','E1–E4 controlled feature ablation'),('Opaque predictions','SHAP explanation with association/causation distinction')])
    h('5.3 Fair comparison')
    p('Comparisons should use the same target definition, holdout transition and metric implementation. Any difference in eligible rows caused by missing modalities must be reported. Improvements will be stated only after the common evaluation protocol has been run.')

    chapter(6,'Proposed System')
    h('6.1 Data and preprocessing')
    p('The pipeline reads existing raw Sentinel-2 L2A archives from Backblaze B2. It does not acquire another copy from the original provider. Scene selection is based on study-area usability. Required bands are extracted to a frozen 10 m grid, metadata offsets are applied and separate reflectance and SCL COGs are produced. Per-band DN-zero validity remains independent of the SCL mask.')
    p('Eight selected scenes per epoch feed masked median compositing. SCL classes 4, 5, 6 and 7 are valid; class 2 is conservatively excluded. Cloud, shadow and snow classes receive circular two-pixel dilation. Each output composite pixel requires at least four valid observations, and every epoch must cover at least 99% of the AOI at that threshold. Observation counts remain available for later quality analysis.')
    h('6.2 Features and controlled experiments')
    table('Table 6.1. Planned ablation design',('Experiment','Feature groups'),[('E1','Satellite only'),('E2','Satellite + population'),('E3','Satellite + population + roads/accessibility'),('E4','Full multimodal set including terrain and additional infrastructure context')])
    p('Spectral indices are the next implementation part. NDVI, NDBI, NDWI, MNDWI and BSI will use guarded division and explicit nodata propagation. Feature aggregation will retain coverage and missingness information instead of treating absent measurements as zero.')
    h('6.3 Learning and interpretation')
    p('Training transitions are 2018–2020 and 2020–2022; 2022–2024 is reserved as the temporal holdout. Spatial blocks will be applied within training evaluation. The planned metrics include PR-AUC, F1, ROC-AUC, Cohen’s kappa and Brier score. SHAP analysis follows model selection, with uncertainty and stability checks where feasible.')
    h('6.4 Scenario outputs')
    p('The 2030 scenario has a six-year horizon, longer than the two-year training transitions. Its probability interpretation must therefore be resolved and its extrapolation caveat recorded. The planned Infrastructure Pressure Index combines growth likelihood with accessibility deficits, comparing equal-weighted and entropy-weighted formulations.')

    chapter(7,'System Architecture')
    p('Figure 7.1 separates data provenance, quality-controlled preprocessing, feature/label construction, model evaluation and decision-support outputs. Solid borders identify implemented components through Part 3.5; dashed borders identify planned components. Arrows represent logical data dependencies, not unvalidated deployment behavior.')
    doc.add_picture(str(OUT/'system_architecture.png'),width=Cm(16.0))
    cap=doc.add_paragraph('Figure 7.1. End-to-end research architecture. Solid: implemented through Part 3.5; dashed: planned.',style='Caption');cap.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break();doc.add_heading('7.1 RUNTIME AND STORAGE ARCHITECTURE',2)
    doc.add_picture(str(OUT/'runtime_architecture.png'),width=Cm(16.5))
    doc.add_paragraph('Figure 7.2. Separation of local control, Modal computation and durable B2 storage.',style='Caption')
    p('The local repository contains source code, configuration and documentation. Modal provides the compute and test environment. Worker disk is temporary scratch; B2 contains the durable raw data, processed COGs and manifests. Credentials are injected through a named secret and do not belong in the report or repository. New output contracts use distinct prefixes to preserve legacy products.')
    h('7.2 Validation boundaries')
    p('Each processing contract defines band order, nodata, grid and provenance. Before publication, outputs undergo coverage and COG checks. An independent read-only audit streams the published bytes, verifies SHA-256 identities and checks composite/count agreement at pixel level. These checks validate file integrity and policy consistency; they do not replace future accuracy assessment of built-up labels or growth predictions.')
    h('7.3 Reproducibility and failure handling')
    p('Processing is organized into bounded units with explicit validation gates. Destination collisions cause a stop; existing results are preserved. Manifests and object identities provide provenance. A later reproducibility phase will test reconstruction from the repository and durable B2 artifacts. The report does not claim that this complete end-to-end reconstruction has already been performed.')

    chapter(8,'Tools and Technologies Used')
    table('Table 8.1. Implementation stack and responsibilities',('Technology','Role','Status'),[('Python 3.12','Processing and validation language','In use'),('Modal','Remote compute and regression tests','In use'),('Backblaze B2 / S3 API','Persistent raw and processed objects','In use'),('GDAL / Rasterio','Windowed reads, aligned rasters and COG I/O','In use'),('NumPy / Dask','Array processing and bounded compositing primitives','In use'),('GeoPandas / Shapely / PyProj','Boundary geometry and projected coordinates','In use'),('rio-cogeo','Strict Cloud-Optimized GeoTIFF validation','In use'),('Pytest','Unit and regression testing','In use'),('scikit-learn / XGBoost / LightGBM','Baselines and tree-based experiments','Planned modeling'),('SHAP','Model explanation','Planned'),('Git / GitHub','Source history and documentation','In use')])
    h('8.1 Selection rationale')
    p('Windowed raster access avoids staging the entire raw archive. COGs support partial reads and consistent downstream access. The separation between temporary computation and persistent storage supports worker replacement without discarding the source data. Python libraries provide a common interface for raster, vector and tabular stages, while explicit contracts reduce implicit conversion and alignment errors.')
    h('8.2 Resource discipline')
    p('The deployed composite build processes at most two epochs concurrently with 512-pixel chunks. Dilation halos extend each chunk by two pixels for mask continuity. Raw archives remain in B2, and neither remote processing nor this report requires a second permanent local copy. Actual runtime and account charges must be obtained from run records rather than inferred from output size alone.')

    chapter(9,'Dataset Details and Current Validation')
    table('Table 9.1. Dataset inventory and use',('Dataset','Coverage / resolution','Purpose'),[('Sentinel-2 L2A','280 archived scenes; four epochs; 32 selected','Six-band reflectance and SCL'),('GVMC boundary','Verified OSM polygon; 5 km buffer','Spatial scope and clipping'),('WorldPop','Epoch-specific population inputs; alignment to be checked','Population context'),('OpenStreetMap','Acquired roads and amenities; snapshot date must be recorded','Accessibility and infrastructure'),('Copernicus GLO-30','30 m source elevation','Elevation and derived terrain'),('ESA WorldCover','10 m, 2021 source product','Auxiliary validation / context; temporal limits apply')])
    p('The raw Sentinel-2 archive totals 182.82 GB. Only tile T44QQE is strictly required for the configured study buffer. The processing grid is 5866 × 5417 pixels, EPSG:32644, with 10 m resolution and bounds [706610, 1936220, 765270, 1990390]. The buffered AOI contains 15,353,996 raster pixels. A rectangular raster grid also includes pixels outside the polygon; these are explicitly nodata.')
    h('9.1 Final composite coverage')
    table('Table 9.2. Independently audited coverage at ≥4 observations',('Epoch','Sufficient pixels','AOI coverage','Median count'),[('2018','15,303,223','99.6693%','8'),('2020','15,340,292','99.9107%','8'),('2022','15,323,080','99.7986%','6'),('2024','15,257,709','99.3729%','4')])
    p('All four epochs passed the approved 99% coverage gate. The 2024 median count of four indicates lower observation redundancy than 2018 and 2020 despite adequate combined coverage. Five required observations would retain only about 45.87% of the 2024 AOI, which motivated the approved four-observation policy. This selection does not guarantee equal uncertainty across epochs.')
    doc.add_page_break();doc.add_heading('9.2 OUTPUT INTEGRITY AND LIMITATIONS',2)
    p('The production build published eight immutable contract-3.5.0 COGs: one six-band composite and one count raster per epoch. Their combined size is 1,468,221,549 bytes. The post-publication audit confirmed exactly one historical/current version per key, streamed hashes matching publication metadata, strict COG structure, expected schemas and matching composite/count validity. All reported audit gates passed.')
    table('Table 9.3. Implementation status at the reporting checkpoint',('Stage','Evidence / remaining work'),[('Acquisition and inventory','Completed and verified'),('Extraction and masking','32 scene pairs; mask policy validated'),('Epoch compositing','Four composite/count pairs; independent audit passed'),('Spectral indices','Next approved implementation part; not started'),('Feature grid and labels','Planned; historical source-date restrictions must be enforced'),('Models and explanations','Planned; no accuracy or SHAP results available'),('2030 and pressure maps','Planned; forecast-horizon interpretation unresolved')])
    h('9.3 Scientific limitations')
    p('SCL can misclassify dark or bright roofs, and a valid observation count is not a substitute for reference-based classification accuracy. Current OSM information cannot automatically represent historical infrastructure. WorldCover 2021 cannot be used as an undated label for all four epochs. NDBI and related indices respond to bare soil as well as built surfaces; label construction therefore needs a separately validated method. Reflectance values outside the nominal physical range were preserved for quality review rather than silently clipped.')
    p('The present checkpoint establishes preprocessing integrity. It does not establish the validity of the future label method, the superiority of multimodal learning, causal explanations or calibrated 2030 forecasts. These remain explicit research tasks.')

    chapter(10,'Conclusion')
    p('The project has established a reproducible foundation for multimodal urban-expansion analysis in Visakhapatnam. The completed stages combine verified spatial scope, an audited raw-data inventory, metadata-based radiometric processing, configurable cloud/shadow masking and observation-count-controlled compositing. Four historical epochs now have independently audited six-band composites with more than 99% coverage at the approved minimum of four observations.')
    p('The next stage is spectral-index generation, followed by a common analysis grid, validated growth labels and leakage-safe dataset construction. Modeling will compare satellite-only and multimodal feature sets under a shared temporal holdout and spatial evaluation protocol. Explanations and infrastructure-pressure outputs will be developed only after the predictive model and temporal assumptions have been assessed.')
    p('The intended outcome is a transparent decision-support framework whose predictions can be inspected and whose limitations remain visible. The 2030 scenario must be presented with its longer forecast horizon and input-date uncertainties, and no planning claim should exceed the supporting validation evidence.')

    chapter(11,'References')
    refs=[
        '[1] M. Marconcini et al., “Outlining where humans live, the World Settlement Footprint 2015,” Scientific Data, vol. 7, article 242, 2020, doi: 10.1038/s41597-020-00580-5. https://www.nature.com/articles/s41597-020-00580-5',
        '[2] D. R. Roberts et al., “Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure,” Ecography, vol. 40, pp. 913–929, 2017, doi: 10.1111/ecog.02881. https://doi.org/10.1111/ecog.02881',
        '[3] S. M. Lundberg and S.-I. Lee, “A unified approach to interpreting model predictions,” in Advances in Neural Information Processing Systems, vol. 30, 2017. https://proceedings.neurips.cc/paper_files/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html',
    ]
    for ref in refs:
        para=p(ref)
        for run in para.runs:run.font.size=Pt(11)
    h('Project evidence')
    p('Repository records: plan.md; configs/temporal.yaml; configs/preprocessing.yaml; results/phase3/mask_validation.md; results/phase3/composite_validation.md. Operational evidence was supplied by the successful Modal build and independent read-only audit runs. These records support the current implementation facts and are separate from the external research references.')
    p('Reporting checkpoint: 6 November 2026. Replace bracketed identity fields, review the declaration/certificate, and obtain guide approval before academic submission.')

    # Number the body from chapter 1; preliminary section uses roman numerals.
    # Word fields keep pagination correct when the document is opened or exported.
    preliminary=doc.sections[0]
    numbering=OxmlElement('w:pgNumType');numbering.set(qn('w:fmt'),'lowerRoman')
    preliminary._sectPr.append(numbering)
    for section in doc.sections:
        footer=section.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
        fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
    settings=doc.settings.element
    update=OxmlElement('w:updateFields');update.set(qn('w:val'),'true');settings.append(update)
    destination=OUT/'Vizag_GeoAI_Project_Report_Reviewed.docx'
    if destination.exists():raise FileExistsError(destination)
    doc.save(destination)
    print(destination)
    print(f'Paragraphs: {len(doc.paragraphs)}; tables: {len(doc.tables)}; figures: {len(doc.inline_shapes)}')

if __name__=='__main__':build()

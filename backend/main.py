"""HTTP boundary: validate input, call the analyzer, and serve the interface."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from .analyzer import AnalysisError, analyze
from .models import AnalyzeRequest, Anatomy

app = FastAPI(title='Python Anatomy', version='0.5.0')
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@app.get('/health')
def health():
    """Let the hosting service confirm that the web application is running."""
    return {'status': 'ok'}


@app.post('/analyze', response_model=Anatomy)
def analyze_source(request: AnalyzeRequest):
    try:
        return analyze(request.source)
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/examples/mini-store', response_class=PlainTextResponse)
def mini_store_source():
    """Keep the displayed lesson and tested Python example in one source file."""
    return (PROJECT_ROOT / 'examples' / 'mini_store.py').read_text(encoding='utf-8')


@app.middleware('http')
async def refresh_local_frontend(request, call_next):
    # Local development should never combine old JS/CSS with a newer analyzer.
    response = await call_next(request)
    if request.url.path in ('/', '/index.html', '/app.js', '/styles.css', '/examples/mini-store'):
        response.headers['Cache-Control'] = 'no-store'
    return response


app.mount('/', StaticFiles(directory=PROJECT_ROOT / 'frontend', html=True), name='frontend')

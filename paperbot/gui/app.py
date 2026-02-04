"""FastAPI + HTMX GUI for PaperBot."""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paperbot.config import Settings
from paperbot.database.repository import PaperRepository
from paperbot.models.paper import Paper
from paperbot.services.crossref_service import CrossrefService
from paperbot.services.export_service import MarkdownExporter
from paperbot.services.feed_service import FeedService


# Global state for services
class AppState:
    settings: Settings
    repo: PaperRepository
    crossref: CrossrefService
    feed_service: FeedService
    exporter: MarkdownExporter
    fetch_status: dict = {"running": False, "message": "", "complete": False}


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    state.settings = Settings.load()
    state.repo = PaperRepository(state.settings.db_path)
    state.crossref = CrossrefService(state.settings.contact_email)
    state.feed_service = FeedService(
        feeds_path=state.settings.feeds_path,
        crossref=state.crossref,
    )
    state.exporter = MarkdownExporter(state.settings.export_dir)
    state.fetch_status = {"running": False, "message": "", "complete": False}
    yield


# Setup templates
base_dir = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

app = FastAPI(lifespan=lifespan)


# ============================================================================
# Main Pages
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page."""
    stats = state.repo.get_status_counts()
    journals = state.repo.get_distinct_journals()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "journals": journals,
            "active_tab": "new",
        },
    )


# ============================================================================
# Paper List Endpoints (HTMX partials)
# ============================================================================


@app.get("/papers/new", response_class=HTMLResponse)
async def papers_new(
    request: Request,
    q: str = Query("", description="Search query"),
    journal: str = Query("", description="Journal filter"),
):
    """Get new papers list (partial for HTMX)."""
    journal_filter = journal if journal else None
    papers = state.repo.find_by_status("new", limit=200, sort_by="id", journal=journal_filter)
    
    # Filter by search query if provided
    if q:
        q_lower = q.lower()
        papers = [
            p for p in papers
            if q_lower in (p.title or "").lower()
            or q_lower in (p.journal or "").lower()
            or q_lower in (p.authors or "").lower()
        ]
    
    return templates.TemplateResponse(
        "partials/paper_list.html",
        {"request": request, "papers": papers, "tab": "new", "empty_message": "새로운 논문이 없습니다. Fetch New 버튼을 클릭하세요."},
    )


@app.get("/papers/picked", response_class=HTMLResponse)
async def papers_picked(request: Request, q: str = Query("")):
    """Get picked papers list (partial for HTMX)."""
    papers = state.repo.find_picked(limit=100)
    
    if q:
        q_lower = q.lower()
        papers = [
            p for p in papers
            if q_lower in (p.title or "").lower()
            or q_lower in (p.journal or "").lower()
        ]
    
    return templates.TemplateResponse(
        "partials/paper_list.html",
        {"request": request, "papers": papers, "tab": "picked", "empty_message": "선택된 논문이 없습니다."},
    )


@app.get("/papers/archive", response_class=HTMLResponse)
async def papers_archive(
    request: Request,
    q: str = Query(""),
    journal: str = Query(""),
):
    """Get archived papers list (partial for HTMX)."""
    journal_filter = journal if journal else None
    papers = state.repo.find_all(limit=500, sort_by="date", journal=journal_filter)
    
    if q:
        q_lower = q.lower()
        papers = [
            p for p in papers
            if q_lower in (p.title or "").lower()
            or q_lower in (p.journal or "").lower()
        ]
    
    return templates.TemplateResponse(
        "partials/paper_list.html",
        {"request": request, "papers": papers, "tab": "archive", "empty_message": "논문이 없습니다."},
    )


# ============================================================================
# Paper Detail
# ============================================================================


@app.get("/papers/{paper_id}", response_class=HTMLResponse)
async def paper_detail(request: Request, paper_id: int):
    """Get paper detail view (partial for HTMX)."""
    papers = state.repo.find_all(limit=10000)
    paper = next((p for p in papers if p.id == paper_id), None)
    
    if not paper:
        return HTMLResponse("<div class='p-8 text-center text-slate-500'>논문을 찾을 수 없습니다.</div>")
    
    return templates.TemplateResponse(
        "partials/detail.html",
        {"request": request, "paper": paper},
    )


# ============================================================================
# Stats Endpoint
# ============================================================================


@app.get("/stats", response_class=HTMLResponse)
async def get_stats(request: Request):
    """Get stats partial for sidebar."""
    stats = state.repo.get_status_counts()
    return templates.TemplateResponse(
        "partials/stats.html",
        {"request": request, "stats": stats},
    )


# ============================================================================
# Actions: Fetch, Export, Pick/Unpick
# ============================================================================


def _do_fetch():
    """Background task to fetch papers."""
    state.fetch_status = {"running": True, "message": "RSS 피드 수집 중...", "complete": False}
    
    try:
        archived = state.repo.archive_old_new()
        total_new = 0
        total_processed = 0
        workers = min(8, (os.cpu_count() or 2) - 1)
        workers = max(1, workers)
        
        for paper in state.feed_service.fetch_all(max_workers=workers):
            if state.repo.upsert(paper):
                total_new += 1
            total_processed += 1
        
        state.fetch_status = {
            "running": False,
            "message": f"완료: {total_new}개 신규, {total_processed}개 처리됨" + (f" ({archived}개 아카이브됨)" if archived > 0 else ""),
            "complete": True,
        }
    except Exception as e:
        state.fetch_status = {"running": False, "message": f"오류: {str(e)}", "complete": True}


@app.post("/actions/fetch", response_class=HTMLResponse)
async def fetch_papers(request: Request, background_tasks: BackgroundTasks):
    """Start fetching new papers."""
    if state.fetch_status.get("running"):
        return templates.TemplateResponse(
            "partials/fetch_status.html",
            {"request": request, "status": state.fetch_status},
        )
    
    background_tasks.add_task(_do_fetch)
    state.fetch_status = {"running": True, "message": "시작 중...", "complete": False}
    
    return templates.TemplateResponse(
        "partials/fetch_status.html",
        {"request": request, "status": state.fetch_status},
    )


@app.get("/actions/fetch-status", response_class=HTMLResponse)
async def fetch_status(request: Request):
    """Get current fetch status."""
    return templates.TemplateResponse(
        "partials/fetch_status.html",
        {"request": request, "status": state.fetch_status},
    )


@app.post("/actions/export", response_class=HTMLResponse)
async def export_picked(request: Request):
    """Export picked papers to markdown."""
    picked_papers = state.repo.find_picked()
    
    if not picked_papers:
        return HTMLResponse(
            """<div class="px-4 py-2 bg-yellow-100 text-yellow-800 rounded-lg text-sm">
                선택된 논문이 없습니다.
            </div>"""
        )
    
    try:
        filepath = state.exporter.export(picked_papers)
        paper_ids = [p.id for p in picked_papers if p.id is not None]
        state.repo.mark_exported(paper_ids)
        
        return HTMLResponse(
            f"""<div class="px-4 py-2 bg-green-100 text-green-800 rounded-lg text-sm">
                {len(picked_papers)}개 논문 내보내기 완료!
            </div>"""
        )
    except Exception as e:
        return HTMLResponse(
            f"""<div class="px-4 py-2 bg-red-100 text-red-800 rounded-lg text-sm">
                오류: {str(e)}
            </div>"""
        )


@app.post("/actions/pick/{paper_id}", response_class=HTMLResponse)
async def pick_paper(request: Request, paper_id: int):
    """Toggle pick status for a paper."""
    # Check current status
    papers = state.repo.find_all(limit=10000)
    paper = next((p for p in papers if p.id == paper_id), None)
    
    if paper:
        if paper.is_picked:
            state.repo.unpick([paper_id])
        else:
            state.repo.pick([paper_id])
    
    # Return updated checkbox
    new_picked = not paper.is_picked if paper else False
    return HTMLResponse(
        f"""<input type="checkbox" 
            class="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer" 
            hx-post="/actions/pick/{paper_id}"
            hx-swap="outerHTML"
            hx-trigger="click"
            {"checked" if new_picked else ""}>"""
    )


@app.post("/actions/pick-all", response_class=HTMLResponse)
async def pick_all(request: Request, ids: str = Form(...)):
    """Pick multiple papers by IDs."""
    try:
        paper_ids = [int(x) for x in ids.split(",") if x.strip()]
        if paper_ids:
            state.repo.pick(paper_ids)
        return HTMLResponse('<span class="text-green-600 text-sm">선택됨!</span>')
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-600 text-sm">오류: {str(e)}</span>')


@app.post("/actions/unpick-all", response_class=HTMLResponse)
async def unpick_all(request: Request, ids: str = Form(...)):
    """Unpick multiple papers by IDs."""
    try:
        paper_ids = [int(x) for x in ids.split(",") if x.strip()]
        if paper_ids:
            state.repo.unpick(paper_ids)
        return HTMLResponse('<span class="text-green-600 text-sm">선택 해제됨!</span>')
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-600 text-sm">오류: {str(e)}</span>')


# ============================================================================
# Journal Filter
# ============================================================================


@app.get("/journals", response_class=HTMLResponse)
async def get_journals(request: Request):
    """Get journal options for filter dropdown."""
    journals = state.repo.get_distinct_journals()
    options = ['<option value="">전체 저널</option>']
    for j in journals:
        options.append(f'<option value="{j}">{j}</option>')
    return HTMLResponse("\n".join(options))
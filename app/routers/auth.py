import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.config import get_settings

router = APIRouter()


def is_admin(request: Request) -> bool:
    """Shared-password session gate (standards §9 single-operator pattern)."""
    return bool(request.session.get("is_admin"))


@router.get("/login")
async def login_page(request: Request):
    if is_admin(request):
        return RedirectResponse(f"{get_settings().root_path}/", status_code=303)
    return request.app.state.templates.TemplateResponse(
        request, "login.html", {"error": False}
    )


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    password = (form.get("password") or "").strip()
    configured = get_settings().search_password
    if configured and secrets.compare_digest(password, configured):
        request.session["is_admin"] = True
        return RedirectResponse(f"{get_settings().root_path}/", status_code=303)
    return request.app.state.templates.TemplateResponse(
        request, "login.html", {"error": True}, status_code=401
    )


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(f"{get_settings().root_path}/login", status_code=303)
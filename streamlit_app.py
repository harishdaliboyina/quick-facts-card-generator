import io
import zipfile

import openpyxl
import streamlit as st

from core import generate_card, DEFAULT_API_BASE, DEFAULT_MODEL

st.set_page_config(page_title="Quick Facts Card Generator", page_icon="🍓", layout="wide")


def get_api_key():
    try:
        return st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        return ""


def get_api_base():
    try:
        return st.secrets.get("API_BASE", DEFAULT_API_BASE)
    except Exception:
        return DEFAULT_API_BASE


def get_model():
    try:
        return st.secrets.get("MODEL", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL


if "generated" not in st.session_state:
    st.session_state.generated = {}  # filename -> bytes
if "last_batch" not in st.session_state:
    st.session_state.last_batch = []  # list of filenames from the latest bulk run

st.title("🍓 Quick Facts Card Generator")
st.caption("F&V Quick Facts infographics — draft, generate, package")

api_key = get_api_key()
if not api_key:
    st.info(
        "This is the reliable, fast template version of the card generator. "
        "(AI-designed cards need Talabat's internal network and aren't available on this "
        "public link — provide a Reference Image URL and fill in the facts below for best results.)"
    )

tab_single, tab_bulk = st.tabs(["Single Item", "Bulk Upload"])

with tab_single:
    col_form, col_preview = st.columns([1, 1])

    with col_form:
        mpc = st.text_input("MPC", value="6ac4e5c4656c7e565917cf34")
        item_name = st.text_input("Item Name", value="Strawberry Korea, 250g")
        display_title = st.text_input(
            "Card Title (optional)",
            value="",
            placeholder='Leave blank to auto-simplify, e.g. "Strawberry"',
        )
        image_url = st.text_input(
            "Reference Image URL (optional)",
            value="https://talabat.dhmedia.io/image/product-information-management/6ac4e5c0656c7e565917c337.jpg",
            help="Leave blank to generate the photo purely from the item name.",
        )

        c1, c2 = st.columns(2)
        with c1:
            profile = st.text_area("Profile (optional)", value="Sweet and fragrant with a lovely berry aroma")
            best_uses = st.text_area("Best Uses (optional)", value="Great for snacking, desserts, smoothies and fruit platters")
        with c2:
            texture = st.text_area("Texture (optional)", value="Juicy and firm with a glossy skin")
            origin = st.text_area("Origin & Advantage (optional)", value="A premium variety, naturally sweeter and larger than regular strawberries")

        skip_ai_design = st.checkbox(
            "Skip AI design and use the simple coded template instead",
            help="Faster and glitch-free, but less visually rich.",
        )

        with st.expander("Advanced: API settings"):
            api_base = st.text_input("API Base URL", value=get_api_base())
            model = st.text_input("Model", value=get_model())

        generate_clicked = st.button("Generate Card", type="primary")

    with col_preview:
        st.subheader("Preview")
        if generate_clicked:
            with st.spinner("Generating…"):
                ok, png_bytes, fname, msg = generate_card(
                    mpc, item_name, image_url, profile, texture, best_uses, origin,
                    api_key=api_key, api_base=api_base, model=model,
                    skip_ai_design=skip_ai_design, display_title=display_title,
                )
            if not ok:
                st.error(msg)
            else:
                st.session_state.generated[fname] = png_bytes
                if msg:
                    st.info(msg)
                st.image(png_bytes, use_container_width=True)
                st.download_button("Download PNG", data=png_bytes, file_name=fname, mime="image/png")
        elif st.session_state.generated:
            last_fname = list(st.session_state.generated.keys())[-1]
            st.image(st.session_state.generated[last_fname], use_container_width=True)
            st.download_button(
                "Download PNG", data=st.session_state.generated[last_fname],
                file_name=last_fname, mime="image/png",
            )
        else:
            st.info("Your generated card will appear here.")

    if st.session_state.generated:
        st.subheader("Generated So Far")
        for fname in sorted(st.session_state.generated):
            cols = st.columns([4, 1])
            cols[0].write(fname)
            cols[1].download_button(
                "Download", data=st.session_state.generated[fname], file_name=fname,
                mime="image/png", key=f"dl_{fname}",
            )

with tab_bulk:
    st.write(
        "Excel (.xlsx) with columns **MPC**, **Item Name** "
        "(optional: Reference Image URL, Card Title, Profile, Texture, Best Uses, Origin & Advantage — "
        "any blank fact fields are auto-generated from the item name)."
    )

    def build_template_bytes():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Quick Facts"
        headers = ["MPC", "Item Name", "Reference Image URL", "Card Title",
                   "Profile", "Texture", "Best Uses", "Origin & Advantage"]
        ws.append(headers)
        ws.append([
            "6ac4e5c4656c7e565917cf34", "Strawberry Korea, 250g",
            "https://talabat.dhmedia.io/image/product-information-management/6ac4e5c0656c7e565917c337.jpg",
            "Strawberry", "Sweet and fragrant with a lovely berry aroma",
            "Juicy and firm with a glossy skin",
            "Great for snacking, desserts, smoothies and fruit platters",
            "A premium variety, naturally sweeter and larger than regular strawberries",
        ])
        ws.append(["TEST-APPLE-002", "Royal Gala Apple, 500g", "", "", "", "", "", ""])
        for i in range(1, len(headers) + 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 30
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    st.download_button(
        "⬇ Download Excel template with correct headers",
        data=build_template_bytes(),
        file_name="quick_facts_bulk_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    uploaded = st.file_uploader("Upload filled-in Excel file", type=["xlsx"])
    bulk_skip_ai = st.checkbox("Skip AI design for this batch (simple template)", key="bulk_skip_ai")

    REQUIRED_COLS = {"mpc", "item name"}
    OPTIONAL_COLS = {
        "profile": "profile", "texture": "texture", "best uses": "best_uses",
        "origin & advantage": "origin", "origin and advantage": "origin",
        "card title": "display_title", "display title": "display_title",
    }

    if st.button("Generate All From Excel") and uploaded is not None:
        wb = openpyxl.load_workbook(uploaded, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if not rows:
            st.error("The sheet is empty.")
        else:
            header = [str(c).strip().lower() if c else "" for c in rows[0]]
            col_index = {name: i for i, name in enumerate(header)}
            missing = REQUIRED_COLS - set(header)
            if missing:
                st.error(f"Missing required column(s): {', '.join(sorted(missing))}. Expected headers: MPC, Item Name.")
            else:
                opt_index = {field: col_index[h] for h, field in OPTIONAL_COLS.items() if h in col_index}
                img_col = col_index.get("reference image url")
                results = []
                progress = st.progress(0.0)
                data_rows = [r for r in rows[1:] if r and not all(c is None for c in r)]
                for i, row in enumerate(data_rows):
                    mpc_v = str(row[col_index["mpc"]]).strip() if row[col_index["mpc"]] is not None else ""
                    item_name_v = str(row[col_index["item name"]]).strip() if row[col_index["item name"]] is not None else ""
                    image_url_v = str(row[img_col]).strip() if img_col is not None and row[img_col] is not None else ""

                    def opt(field):
                        idx = opt_index.get(field)
                        if idx is None or row[idx] is None:
                            return ""
                        return str(row[idx]).strip()

                    ok, png_bytes, fname, msg = generate_card(
                        mpc_v, item_name_v, image_url_v,
                        opt("profile"), opt("texture"), opt("best_uses"), opt("origin"),
                        api_key=api_key, api_base=get_api_base(), model=get_model(),
                        skip_ai_design=bulk_skip_ai, display_title=opt("display_title"),
                    )
                    results.append({"mpc": mpc_v, "ok": ok, "file": fname, "msg": msg})
                    if ok:
                        st.session_state.generated[fname] = png_bytes
                    progress.progress((i + 1) / len(data_rows))

                ok_count = sum(1 for r in results if r["ok"])
                st.success(f"{ok_count} of {len(results)} items generated.")
                for r in results:
                    if not r["ok"]:
                        st.error(f"{r['mpc'] or '(no MPC)'}: {r['msg']}")
                    elif r["msg"]:
                        st.warning(f"{r['file']}: {r['msg']}")

                st.session_state.last_batch = [r["file"] for r in results if r["ok"]]

    if st.session_state.last_batch:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in st.session_state.last_batch:
                if fname in st.session_state.generated:
                    zf.writestr(fname, st.session_state.generated[fname])
        buf.seek(0)
        st.download_button(
            "Download This Batch as ZIP", data=buf.getvalue(),
            file_name="quick_facts_batch.zip", mime="application/zip",
        )

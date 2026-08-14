from __future__ import annotations

import base64
import json
import time
import uuid
from html import escape
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from report_export import build_report, get_standard_texts
from storage import (
    authenticate_user,
    change_password,
    create_complex,
    create_project,
    create_report,
    delete_finding,
    get_user,
    init_db,
    insert_finding,
    list_complexes,
    list_findings,
    list_projects,
    list_reports,
    load_complex,
    load_project,
    load_report,
    register_user,
    save_report,
    update_complex,
    update_finding,
    update_project,
)


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHOICES_PATH = DATA_DIR / "choices.json"
TEMPLATE_PATH = APP_DIR / "templates" / "rapportage_brandveiligheid_template.docx"
LOGO_PATH = APP_DIR / "assets" / "triacon-logo.png"
SESSION_TIMEOUT_SECONDS = 12 * 60 * 60

BUILDING_FIELDS = [
    ("bouwjaar", "Bouwjaar"),
    ("aantal_bouwlagen", "Aantal bouwlagen"),
    ("aantal_woningen", "Aantal woningen"),
    ("grondgebonden", "Grondgebonden"),
    ("portiek", "Portiek"),
    ("galerij", "Galerij"),
    ("corridor", "Corridor"),
    ("atrium", "Atrium"),
    ("lift", "Lift"),
]

INSTALLATION_FIELDS = [
    ("brandmeldinstallatie", "Brandmeld- en ontruimingsalarminstallatie"),
    ("overige_installaties", "Overige installaties aanwezig"),
    ("bouwjaar_installatie", "Bouwjaar installatie"),
    ("pve", "Programma van eisen (PVE)"),
    ("onderhoud_bmi_oai", "Onderhoudsrapportage BMI/OAI"),
    ("onderhoud_blusmiddelen", "Onderhoud gegevens blusmiddelen"),
    ("onderhoud_noodverlichting", "Onderhoud gegevens noodverlichting"),
    ("drukgeregelde_ventilatie", "Drukgeregelde ventilatie aanwezig"),
    ("zelfregelende_ventielen", "Zelfregelende ventilatieventielen aanwezig"),
]

ORGANISATION_FIELDS = [
    ("type_bezit", "Type bezit"),
    ("woonvorm", "Woonvorm"),
    ("zorgzwaarte", "Zorgzwaarte"),
    ("demarcatie", "Demarcatie"),
    ("melding_brandveilig_gebruik", "Melding brandveilig gebruik"),
    ("bhv", "Bedrijfshulpverlening (BHV)"),
    ("ontruimingsplan", "Bedrijfsnood-/ontruimingsplan"),
    ("ontruimingsplattegronden", "Ontruimingsplattegronden"),
]

MATERIAL_FIELDS = [
    ("bouwconstructie", "Bouwconstructie"),
    ("dakconstructie", "Dakconstructie"),
    ("dakisolatie", "Dakisolatie"),
    ("dakbedekking", "Dakbedekking"),
    ("gevels", "Gevels"),
    ("gevelisolatie", "Gevelisolatie"),
    ("scheidingswanden", "Scheidingswanden"),
    ("vloeren", "Vloeren"),
    ("vloerafwerking", "Vloerafwerking"),
    ("verlaagde_plafonds", "Verlaagde plafonds"),
    ("buitenkozijnen", "Buitenkozijnen"),
    ("binnenkozijnen", "Binnenkozijnen"),
    ("buitentrappen", "Buitentrappen"),
]


def load_choices() -> list[dict]:
    if not CHOICES_PATH.exists():
        return []
    return json.loads(CHOICES_PATH.read_text(encoding="utf-8"))


@st.cache_data
def standard_report_texts() -> dict[str, str]:
    return get_standard_texts(TEMPLATE_PATH)


@st.cache_data
def logo_data_uri() -> str:
    if not LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def set_flash(message: str) -> None:
    st.session_state["flash_message"] = message


def show_flash() -> None:
    message = st.session_state.pop("flash_message", None)
    if message:
        st.toast(message, icon="✅")


def save_image(upload, project_id: int, prefix: str) -> str | None:
    if upload is None:
        return None
    target_dir = UPLOAD_DIR / str(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{prefix}-{uuid.uuid4().hex}.jpg"
    image = Image.open(upload)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((1800, 1800))
    image.save(target, "JPEG", quality=86, optimize=True)
    return str(target.relative_to(APP_DIR))


def absolute_photo(relative: str | None) -> str | None:
    if not relative:
        return None
    path = APP_DIR / relative
    return str(path) if path.exists() else None


def input_grid(data: dict, fields: list[tuple[str, str]], prefix: str) -> dict:
    result = {}
    cols = st.columns(2)
    for i, (key, label) in enumerate(fields):
        with cols[i % 2]:
            result[key] = st.text_input(label, value=str(data.get(key, "")), key=f"{prefix}_{key}")
    return result


def session_user_id() -> int:
    return int(st.session_state["user_id"])


def render_auth_page() -> None:
    st.markdown(
        f"""
        <section class="auth-shell">
          <img src="{logo_data_uri()}" alt="TriaCon-logo">
          <h1>Brandveiligheidsinspectie</h1>
          <p>Log in om projecten, complexen en rapporten te beheren.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    login_tab, register_tab = st.tabs(["Inloggen", "Registreren"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("E-mailadres", autocomplete="email")
            password = st.text_input("Wachtwoord", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Inloggen", type="primary", use_container_width=True)
            if submitted:
                user = authenticate_user(email, password)
                if user is None:
                    st.error("E-mailadres of wachtwoord is niet correct.")
                else:
                    st.session_state["user_id"] = int(user["id"])
                    set_flash(f"Welkom {user['name']}.")
                    st.rerun()
    with register_tab:
        with st.form("registration_form"):
            name = st.text_input("Naam", autocomplete="name")
            email = st.text_input("E-mailadres", autocomplete="email", key="register_email")
            password = st.text_input("Wachtwoord", type="password", autocomplete="new-password", key="register_password")
            confirm = st.text_input("Wachtwoord bevestigen", type="password", autocomplete="new-password")
            st.caption("Gebruik minimaal 10 tekens. Wachtwoorden worden uitsluitend gehasht opgeslagen.")
            submitted = st.form_submit_button("Account aanmaken", type="primary", use_container_width=True)
            if submitted:
                if password != confirm:
                    st.error("De wachtwoorden komen niet overeen.")
                else:
                    try:
                        user_id = register_user(name, email, password)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["user_id"] = user_id
                        set_flash("Account succesvol aangemaakt.")
                        st.rerun()


def authenticated_user() -> dict | None:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    now = time.time()
    last_activity = float(st.session_state.get("auth_last_activity", now))
    if now - last_activity > SESSION_TIMEOUT_SECONDS:
        st.session_state.clear()
        st.warning("Uw sessie is verlopen. Log opnieuw in.")
        return None
    st.session_state["auth_last_activity"] = now
    user = get_user(int(user_id))
    if user is None:
        st.session_state.pop("user_id", None)
    return user


def render_account_controls(user: dict) -> None:
    st.markdown(f"**{user['name']}**")
    st.caption(user["email"])
    with st.expander("Account en wachtwoord"):
        with st.form("change_password_form"):
            current = st.text_input("Huidig wachtwoord", type="password")
            new = st.text_input("Nieuw wachtwoord", type="password")
            confirm = st.text_input("Nieuw wachtwoord bevestigen", type="password")
            if st.form_submit_button("Wachtwoord wijzigen", use_container_width=True):
                if new != confirm:
                    st.error("De nieuwe wachtwoorden komen niet overeen.")
                else:
                    try:
                        change_password(int(user["id"]), current, new)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.success("Wachtwoord gewijzigd.")
    if st.button("Uitloggen", use_container_width=True):
        st.session_state.clear()
        st.rerun()


def hierarchy_selector(user: dict) -> dict:
    projects = list_projects()
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        st.markdown('<div class="sidebar-label">BRANDVEILIGHEID</div>', unsafe_allow_html=True)
        render_account_controls(user)
        st.divider()
        st.markdown("### 1. Project")
        with st.expander("＋ Nieuw project"):
            with st.form("new_project_form"):
                name = st.text_input("Projectnaam")
                client = st.text_input("Opdrachtgever")
                number = st.text_input("Projectnummer")
                description = st.text_area("Omschrijving")
                if st.form_submit_button("Project aanmaken", type="primary", use_container_width=True):
                    try:
                        project_id = create_project(name, client, number, description, int(user["id"]))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["selected_project_id"] = project_id
                        st.session_state.pop("selected_complex_id", None)
                        st.session_state.pop("selected_report_id", None)
                        set_flash("Project aangemaakt.")
                        st.rerun()
        if not projects:
            st.info("Maak het eerste project aan.")
            return {}
        project_ids = [int(row["id"]) for row in projects]
        if st.session_state.get("selected_project_id") not in project_ids:
            st.session_state["selected_project_id"] = project_ids[0]
        selected_project_id = st.selectbox(
            "Bestaand project openen",
            project_ids,
            format_func=lambda value: next(row["name"] for row in projects if int(row["id"]) == value),
            key="selected_project_id",
        )
        project = load_project(int(selected_project_id))

        st.markdown("### 2. Complex")
        with st.expander("＋ Nieuw complex"):
            with st.form("new_complex_form"):
                name = st.text_input("Complexnaam")
                number = st.text_input("Complexnummer")
                address = st.text_input("Adres")
                postal_code = st.text_input("Postcode")
                city = st.text_input("Plaats")
                if st.form_submit_button("Complex aanmaken", type="primary", use_container_width=True):
                    try:
                        complex_id = create_complex(int(selected_project_id), name, number, address, postal_code, city, int(user["id"]))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["selected_complex_id"] = complex_id
                        st.session_state.pop("selected_report_id", None)
                        set_flash("Complex aangemaakt.")
                        st.rerun()
        complexes = list_complexes(int(selected_project_id))
        if not complexes:
            st.info("Maak binnen dit project het eerste complex aan.")
            return {"project": project}
        complex_ids = [int(row["id"]) for row in complexes]
        if st.session_state.get("selected_complex_id") not in complex_ids:
            st.session_state["selected_complex_id"] = complex_ids[0]
        selected_complex_id = st.selectbox(
            "Bestaand complex openen",
            complex_ids,
            format_func=lambda value: next(
                f"{row['complex_number'] or '—'} · {row['name']}" for row in complexes if int(row["id"]) == value
            ),
            key="selected_complex_id",
        )
        complex_data = load_complex(int(selected_complex_id))

        st.markdown("### 3. Rapport")
        with st.expander("＋ Nieuw rapport"):
            with st.form("new_report_form"):
                title = st.text_input("Rapportnaam", value="Rapportage brandveiligheid")
                if st.form_submit_button("Rapport aanmaken", type="primary", use_container_width=True):
                    report_id = create_report(int(selected_complex_id), title, int(user["id"]))
                    st.session_state["selected_report_id"] = report_id
                    set_flash("Rapport aangemaakt.")
                    st.rerun()
        reports = list_reports(int(selected_complex_id))
        if not reports:
            st.info("Maak binnen dit complex het eerste rapport aan.")
            return {"project": project, "complex": complex_data}
        report_ids = [int(row["id"]) for row in reports]
        if st.session_state.get("selected_report_id") not in report_ids:
            st.session_state["selected_report_id"] = report_ids[0]
        selected_report_id = st.selectbox(
            "Rapport openen",
            report_ids,
            format_func=lambda value: next(
                f"{row['title']} · {row['status']}" for row in reports if int(row["id"]) == value
            ),
            key="selected_report_id",
        )
        st.caption("Alle inspecteurs werken in dezelfde centrale projectdatabase.")
    return {
        "project": project,
        "complex": complex_data,
        "report": load_report(int(selected_report_id)),
    }


def render_breadcrumbs(context: dict) -> None:
    parts = ["Projecten"]
    if context.get("project"):
        parts.append(context["project"]["name"])
    if context.get("complex"):
        parts.append(context["complex"]["name"])
    if context.get("report"):
        parts.append(context["report"]["title"])
    st.markdown(
        '<nav class="breadcrumbs">' + '<span>›</span>'.join(f"<strong>{escape(str(part))}</strong>" if index == len(parts) - 1 else escape(str(part)) for index, part in enumerate(parts)) + "</nav>",
        unsafe_allow_html=True,
    )


def render_hierarchy_data(context: dict) -> None:
    project = context["project"]
    complex_data = context["complex"]
    st.subheader("Project en complex")
    with st.form("project_data"):
        st.markdown("#### Project")
        p1, p2 = st.columns(2)
        project_name = p1.text_input("Projectnaam", project.get("name", ""))
        client = p2.text_input("Opdrachtgever", project.get("client", ""))
        project_number = p1.text_input("Projectnummer", project.get("project_number", ""))
        description = st.text_area("Omschrijving", project.get("description", ""))
        st.markdown("#### Complex")
        c1, c2 = st.columns(2)
        complex_name = c1.text_input("Complexnaam", complex_data.get("name", ""))
        complex_number = c2.text_input("Complexnummer", complex_data.get("complex_number", ""))
        address = c1.text_input("Adres", complex_data.get("address", ""))
        postal_code = c2.text_input("Postcode", complex_data.get("postal_code", ""))
        city = c2.text_input("Plaats", complex_data.get("city", ""))
        if st.form_submit_button("Project en complex opslaan", type="primary"):
            update_project(int(project["id"]), {
                "name": project_name, "client": client, "project_number": project_number, "description": description,
            })
            update_complex(int(complex_data["id"]), {
                "name": complex_name, "complex_number": complex_number, "address": address,
                "postal_code": postal_code, "city": city,
            })
            set_flash("Project- en complexgegevens opgeslagen.")
            st.rerun()


def render_report_data(project: dict) -> None:
    st.subheader("Rapportgegevens")
    with st.form("report_data"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Rapportnaam", project.get("title", ""))
            kenmerk = st.text_input("Kenmerk", project.get("kenmerk", ""))
            st.text_input("Complex", f"{project.get('complexnummer','')} · {project.get('complexnaam','')}", disabled=True)
            st.text_input("Project", project.get("projectnaam", ""), disabled=True)
        with c2:
            opdrachtgever_adres = st.text_area("Adres opdrachtgever", project.get("opdrachtgever_adres", ""), height=70)
            opdrachtgever_contact = st.text_input("Contactpersoon opdrachtgever", project.get("opdrachtgever_contact", ""))
            inspecteur = st.text_input("Inspecteur(s)", project.get("inspecteur", ""))
            gecontroleerd = st.text_input("Gecontroleerd door", project.get("gecontroleerd", ""))
            triacon_contact = st.text_input("Contactpersoon TriaCon", project.get("triacon_contact", ""))
            triacon_email = st.text_input("E-mail TriaCon", project.get("triacon_email", ""))
        c3, c4, c5 = st.columns(3)
        report_date = c3.text_input("Rapportdatum", project.get("report_date", ""))
        version = c4.text_input("Versie", project.get("version", "0.1"))
        status = c5.selectbox("Status", ["Concept", "Ter controle", "Definitief"], index=["Concept", "Ter controle", "Definitief"].index(project.get("status", "Concept")))
        if st.form_submit_button("Rapportgegevens opslaan", type="primary"):
            project.update({
                "title": title, "kenmerk": kenmerk,
                "opdrachtgever_adres": opdrachtgever_adres,
                "opdrachtgever_contact": opdrachtgever_contact, "inspecteur": inspecteur,
                "gecontroleerd": gecontroleerd, "triacon_contact": triacon_contact,
                "triacon_email": triacon_email, "report_date": report_date,
                "version": version, "status": status,
            })
            save_report(project["id"], project, session_user_id())
            st.success("Rapportgegevens opgeslagen.")


def render_general_data(project: dict) -> None:
    st.subheader("Algemene gegevens")
    with st.form("general_data"):
        algemene_omschrijving = st.text_area("Algemene omschrijving complex", project.get("algemene_omschrijving", ""), height=130)
        st.markdown("#### Gebouwgegevens")
        building = input_grid(project, BUILDING_FIELDS, "building")
        st.markdown("#### Installatietechnische gegevens")
        installation = input_grid(project, INSTALLATION_FIELDS, "installation")
        st.markdown("#### Organisatorische gegevens")
        organisation = input_grid(project, ORGANISATION_FIELDS, "organisation")
        st.markdown("#### Materialenlijst")
        materials = input_grid(project, MATERIAL_FIELDS, "materials")
        texts = standard_report_texts()
        st.markdown("#### Vaste rapportteksten")
        st.caption("Deze teksten komen rechtstreeks uit de Word-template en zijn hier bewust niet vrij bewerkbaar.")
        st.text_area("3.6 Doelstelling van het onderzoek", texts["doelstelling"], height=100, disabled=True)
        st.text_area("3.7 Uitgangspunten", texts["uitgangspunten"], height=150, disabled=True)
        bezochte_woningen = st.text_area("Bezochte woningen", project.get("bezochte_woningen", ""), height=80)
        beperkingen = st.text_area("Beperkingen", project.get("beperkingen", ""), height=80)
        if st.form_submit_button("Algemene gegevens opslaan", type="primary"):
            project.update({"algemene_omschrijving": algemene_omschrijving, "bezochte_woningen": bezochte_woningen, "beperkingen": beperkingen})
            project.update(building)
            project.update(installation)
            project.update(organisation)
            project.update(materials)
            save_report(project["id"], project, session_user_id())
            st.success("Algemene gegevens opgeslagen.")


def render_situation(project: dict) -> None:
    st.subheader("Situatie- en complexfoto’s")
    st.caption("Op een iPad kan ‘Maak foto’ de camera openen. Bestaande JPG- of PNG-bestanden kunnen ook worden gekozen.")
    slots = [("voorgevel", "Voorgevel"), ("kopgevel", "Kopgevel"), ("achtergevel", "Achtergevel"), ("luchtfoto", "Luchtfoto / situatietekening")]
    with st.form("situation_photos"):
        uploads = {}
        cols = st.columns(2)
        for i, (key, label) in enumerate(slots):
            with cols[i % 2]:
                current = absolute_photo(project.get(f"photo_{key}"))
                if current:
                    st.image(current, caption=label, use_container_width=True)
                uploads[key] = st.file_uploader(label, type=["jpg", "jpeg", "png"], key=f"situation_{key}")
        if st.form_submit_button("Situatiefoto’s opslaan", type="primary"):
            for key, upload in uploads.items():
                path = save_image(upload, project["id"], key)
                if path:
                    project[f"photo_{key}"] = path
            save_report(project["id"], project, session_user_id())
            st.success("Situatiefoto’s opgeslagen.")


def render_add_finding(project: dict, choices: list[dict]) -> None:
    st.subheader("Nieuwe bevinding")
    finding_type = st.radio("Soort registratie", ["Maatregel", "Overige bevinding"], horizontal=True)
    labels = ["Vrij invoeren"] + [f"{c['onderwerp']} — {c['gebrek']}" for c in choices]
    selected_label = st.selectbox("Standaard gebrek", labels, index=0)
    choice = {} if selected_label == "Vrij invoeren" else choices[labels.index(selected_label) - 1]
    if choice:
        st.info(f"BBL/eis: {choice.get('artikel','')}\n\nMaatregel: {choice.get('maatregel','')}")

    choice_key = str(labels.index(selected_label))
    with st.form("add_finding", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        code_group = c1.selectbox("Codegroep", ["G", "W"], help="G = gemeenschappelijke ruimte, W = woning")
        discipline = c2.selectbox("Werksoort", ["Bouwkundig", "Installatietechnisch", "Organisatorisch"])
        onderwerp = c3.text_input("Onderwerp", value=choice.get("onderwerp", ""), key=f"new_subject_{choice_key}")
        c4, c5, c6 = st.columns(3)
        tekeningnummer = c4.text_input("Tekeningnummer", "N.v.t.")
        bouwlaag = c5.text_input("Bouwlaag")
        ruimte = c6.text_input("Ruimte(nummer)")
        eis = st.text_area("Eis / artikel BBL", value=choice.get("artikel", ""), height=90, key=f"new_requirement_{choice_key}")
        gebrek = st.text_area("Gebrek / bevinding", value=choice.get("gebrek", ""), height=100, key=f"new_defect_{choice_key}")
        c7, c8 = st.columns(2)
        aantal = c7.text_input("Aantal")
        afmeting = c8.text_input("Afmeting")
        maatregel_label = "Conclusie / advies" if finding_type == "Overige bevinding" else "Maatregel"
        maatregel = st.text_area(maatregel_label, value=choice.get("maatregel", ""), height=110, key=f"new_measure_{choice_key}")
        opmerking = st.text_area("Opmerking", value=choice.get("opmerking", ""), height=80, key=f"new_note_{choice_key}")
        richtlijn = st.text_area("Richtlijn", value=choice.get("richtlijn", ""), height=70, key=f"new_guideline_{choice_key}")
        st.markdown("#### Foto’s")
        p1, p2 = st.columns(2)
        photo_camera = p1.camera_input("Maak inspectiefoto")
        photo_upload = p1.file_uploader("Of kies inspectiefoto", type=["jpg", "jpeg", "png"], key="new_before_upload")
        photo_after = p2.file_uploader("Foto na herstel (optioneel)", type=["jpg", "jpeg", "png"], key="new_after_upload")
        submitted = st.form_submit_button("Bevinding toevoegen", type="primary")
        if submitted:
            if not gebrek.strip():
                st.error("Vul een gebrek of bevinding in.")
            else:
                before_path = save_image(photo_camera or photo_upload, project["id"], "inspectie")
                after_path = save_image(photo_after, project["id"], "herstel")
                insert_finding(project["id"], {
                    "finding_type": finding_type,
                    "code_group": code_group,
                    "discipline": discipline,
                    "onderwerp": onderwerp,
                    "tekeningnummer": tekeningnummer,
                    "bouwlaag": bouwlaag,
                    "ruimte": ruimte,
                    "eis": eis,
                    "gebrek": gebrek,
                    "aantal": aantal,
                    "afmeting": afmeting,
                    "maatregel": maatregel,
                    "opmerking": opmerking,
                    "richtlijn": richtlijn,
                    "photo_before": before_path or "",
                    "photo_after": after_path or "",
                }, session_user_id())
                set_flash("Bevinding succesvol toegevoegd.")
                st.rerun()


def render_findings(project: dict) -> None:
    findings = list_findings(project["id"])
    st.subheader(f"Opgeslagen bevindingen ({len(findings)})")
    if not findings:
        st.info("Nog geen bevindingen toegevoegd.")
        return
    for finding in findings:
        code = f"{finding['code_group']}.{int(finding['code_number']):02d}"
        with st.expander(f"{code} · {finding['discipline']} · {finding['gebrek'][:90]}"):
            c1, c2 = st.columns([1, 2])
            with c1:
                if absolute_photo(finding.get("photo_before")):
                    st.image(absolute_photo(finding["photo_before"]), caption="Inspectie", use_container_width=True)
                if absolute_photo(finding.get("photo_after")):
                    st.image(absolute_photo(finding["photo_after"]), caption="Na herstel", use_container_width=True)
            with c2:
                st.write(f"**Locatie:** {finding.get('bouwlaag','')} · {finding.get('ruimte','')}")
                st.write(f"**Eis:** {finding.get('eis','')}")
                st.write(f"**Aantal / afmeting:** {finding.get('aantal','')} · {finding.get('afmeting','')}")
                st.write(f"**Maatregel:** {finding.get('maatregel','')}")
                if finding.get("opmerking"):
                    st.write(f"**Opmerking:** {finding['opmerking']}")
            st.markdown("#### Bewerken")
            with st.form(f"edit_finding_{finding['id']}"):
                e1, e2, e3 = st.columns(3)
                finding_type = e1.selectbox(
                    "Soort registratie", ["Maatregel", "Overige bevinding"],
                    index=["Maatregel", "Overige bevinding"].index(finding.get("finding_type", "Maatregel")),
                    key=f"edit_type_{finding['id']}",
                )
                code_group = e2.selectbox("Codegroep", ["G", "W"], index=["G", "W"].index(finding.get("code_group", "G")), key=f"edit_group_{finding['id']}")
                code_number = e3.number_input("Volgnummer", min_value=1, value=int(finding.get("code_number") or 1), step=1, key=f"edit_number_{finding['id']}")
                discipline = st.selectbox(
                    "Werksoort", ["Bouwkundig", "Installatietechnisch", "Organisatorisch"],
                    index=["Bouwkundig", "Installatietechnisch", "Organisatorisch"].index(finding.get("discipline", "Bouwkundig")),
                    key=f"edit_discipline_{finding['id']}",
                )
                onderwerp = st.text_input("Onderwerp", finding.get("onderwerp", ""), key=f"edit_subject_{finding['id']}")
                e4, e5, e6 = st.columns(3)
                tekeningnummer = e4.text_input("Tekeningnummer", finding.get("tekeningnummer", ""), key=f"edit_drawing_{finding['id']}")
                bouwlaag = e5.text_input("Bouwlaag", finding.get("bouwlaag", ""), key=f"edit_floor_{finding['id']}")
                ruimte = e6.text_input("Ruimte(nummer)", finding.get("ruimte", ""), key=f"edit_room_{finding['id']}")
                eis = st.text_area("Eis / artikel BBL", finding.get("eis", ""), key=f"edit_req_{finding['id']}")
                gebrek = st.text_area("Gebrek / bevinding", finding.get("gebrek", ""), key=f"edit_defect_{finding['id']}")
                e7, e8 = st.columns(2)
                aantal = e7.text_input("Aantal", finding.get("aantal", ""), key=f"edit_count_{finding['id']}")
                afmeting = e8.text_input("Afmeting", finding.get("afmeting", ""), key=f"edit_size_{finding['id']}")
                maatregel = st.text_area("Maatregel / advies", finding.get("maatregel", ""), key=f"edit_measure_{finding['id']}")
                opmerking = st.text_area("Opmerking", finding.get("opmerking", ""), key=f"edit_note_{finding['id']}")
                richtlijn = st.text_area("Richtlijn", finding.get("richtlijn", ""), key=f"edit_guide_{finding['id']}")
                u1, u2 = st.columns(2)
                new_before = u1.file_uploader("Inspectiefoto vervangen", type=["jpg", "jpeg", "png"], key=f"edit_before_{finding['id']}")
                new_after = u2.file_uploader("Herstelfoto vervangen", type=["jpg", "jpeg", "png"], key=f"edit_after_{finding['id']}")
                save_edit = st.form_submit_button("Wijzigingen opslaan", type="primary")
                if save_edit:
                    before_path = save_image(new_before, project["id"], "inspectie") or finding.get("photo_before", "")
                    after_path = save_image(new_after, project["id"], "herstel") or finding.get("photo_after", "")
                    update_finding(finding["id"], {
                        "finding_type": finding_type, "code_group": code_group, "code_number": code_number,
                        "discipline": discipline, "onderwerp": onderwerp, "tekeningnummer": tekeningnummer,
                        "bouwlaag": bouwlaag, "ruimte": ruimte, "eis": eis, "gebrek": gebrek,
                        "aantal": aantal, "afmeting": afmeting, "maatregel": maatregel,
                        "opmerking": opmerking, "richtlijn": richtlijn,
                        "photo_before": before_path, "photo_after": after_path,
                    }, session_user_id())
                    st.success("Bevinding bijgewerkt.")
                    st.rerun()
            if st.button("Bevinding verwijderen", key=f"delete_{finding['id']}"):
                delete_finding(finding["id"])
                st.rerun()


def render_report(project: dict) -> None:
    st.subheader("Rapport afronden en exporteren")
    with st.form("report_texts"):
        samenvatting = st.text_area("Samenvatting", project.get("samenvatting", ""), height=190)
        conclusie = st.text_area("Conclusie", project.get("conclusie", ""), height=190)
        gelijkwaardigheid = st.text_area("Gelijkwaardigheidsoplossing", project.get("gelijkwaardigheid", ""), height=100)
        if st.form_submit_button("Rapportteksten opslaan", type="primary"):
            project.update({"samenvatting": samenvatting, "conclusie": conclusie, "gelijkwaardigheid": gelijkwaardigheid})
            save_report(project["id"], project, session_user_id())
            st.success("Rapportteksten opgeslagen.")
    findings = list_findings(project["id"])
    missing = []
    for key, label in [("complexnummer", "complexnummer"), ("complexnaam", "complexnaam"), ("projectadres", "projectadres"), ("inspecteur", "inspecteur")]:
        if not project.get(key):
            missing.append(label)
    if missing:
        st.warning("Nog niet ingevuld: " + ", ".join(missing))
    st.metric("Bevindingen in rapport", len(findings))
    if not TEMPLATE_PATH.exists():
        st.error("De Word-template ontbreekt in de appmap.")
        return
    if st.button("Word-rapport voorbereiden", type="primary", use_container_width=True):
        with st.spinner("Rapport wordt opgebouwd…"):
            payload = dict(project)
            for key in ["photo_voorgevel", "photo_kopgevel", "photo_achtergevel", "photo_luchtfoto"]:
                payload[key] = absolute_photo(project.get(key))
            for finding in findings:
                finding["photo_before"] = absolute_photo(finding.get("photo_before"))
                finding["photo_after"] = absolute_photo(finding.get("photo_after"))
            content = build_report(TEMPLATE_PATH, payload, findings)
            st.session_state.report_bytes = content
            st.session_state.report_name = f"{project.get('kenmerk') or 'concept'} Rapportage brandveiligheid {project.get('complexnaam') or ''}.docx".strip()
    if st.session_state.get("report_bytes"):
        st.download_button(
            "Download Word-rapport",
            data=st.session_state.report_bytes,
            file_name=st.session_state.get("report_name", "rapportage_brandveiligheid.docx"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            use_container_width=True,
        )
        st.caption("Open het document in Microsoft Word en werk de inhoudsopgave bij met Ctrl+A en F9.")


def render_dashboard(context: dict) -> None:
    project = context.get("project")
    complex_data = context.get("complex")
    report = context.get("report")
    findings = list_findings(report["id"]) if report else []
    projects = list_projects()
    measures = sum(f.get("finding_type") == "Maatregel" for f in findings)
    other = len(findings) - measures
    photos = sum(bool(f.get("photo_before")) + bool(f.get("photo_after")) for f in findings)
    title = report.get("title") if report else (complex_data.get("name") if complex_data else (project.get("name") if project else "Projectomgeving"))
    subtitle = (
        f"{report.get('complexnummer') or 'Nog geen complexnummer'} · {report.get('status') or 'Concept'}"
        if report else "Kies achtereenvolgens een project, complex en rapport in de sidebar."
    )
    st.markdown(
        f"""
        <section class="dashboard-hero">
          <img src="{logo_data_uri()}" alt="TriaCon-logo">
          <div><span>Brandveiligheidsinspectie</span><h2>{escape(str(title))}</h2>
          <p>{escape(str(subtitle))}</p></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projecten", len(projects))
    c2.metric("Complexen", sum(int(item["complex_count"]) for item in projects))
    c3.metric("Rapporten", sum(int(item["report_count"]) for item in projects))
    c4.metric("Bevindingen actief rapport", len(findings))
    st.markdown("### Werkstroom")
    st.info("Dashboard → Project kiezen → Complex kiezen → Rapport openen → Inspectie uitvoeren → Word-rapport genereren.")
    st.markdown("### Projectoverzicht")
    if not projects:
        st.info("Er zijn nog geen projecten. Maak het eerste project aan in de sidebar.")
        return
    for item in projects:
        with st.expander(f"{item['name']} · {item['complex_count']} complex(en) · {item['report_count']} rapport(en)"):
            complexes = list_complexes(int(item["id"]))
            if not complexes:
                st.caption("Nog geen complexen.")
            for complex_row in complexes:
                st.markdown(f"**└─ {complex_row['complex_number'] or '—'} · {complex_row['name']}**")
                reports = list_reports(int(complex_row["id"]))
                if not reports:
                    st.caption("　└─ Nog geen rapport")
                for report_row in reports:
                    st.caption(f"　└─ {report_row['title']} · {report_row['status']}")
    if report:
        st.markdown("### Actief rapport")
        r1, r2, r3 = st.columns(3)
        r1.metric("Maatregelen", measures)
        r2.metric("Overige bevindingen", other)
        r3.metric("Gekoppelde foto's", photos)


def main() -> None:
    st.set_page_config(page_title="TriaCon Brandveiligheidsinspectie", page_icon="🔴", layout="wide")
    logo = logo_data_uri()
    st.markdown(
        f"""
        <style>
        :root{{--tria-indigo:#262362;--tria-red:#ee2b4d;--tria-orange:#f3991e;--tria-soft:#f7f6fb;--tria-line:#e2e0ec}}
        .stApp{{background:linear-gradient(180deg,#ffffff 0,#fbfaff 100%);color:var(--tria-indigo)}}
        .block-container{{max-width:1180px;padding-top:1.1rem;padding-bottom:4rem}}
        [data-testid="stSidebar"]{{background:#f4f3f9;border-right:1px solid var(--tria-line)}}
        [data-testid="stSidebar"] img{{max-width:220px;margin:.3rem auto .7rem}}
        .sidebar-label{{color:var(--tria-red);font-size:.72rem;font-weight:800;letter-spacing:.16em;margin-bottom:.6rem}}
        .triacon-header{{display:flex;align-items:center;gap:1.4rem;padding:1rem 1.35rem;margin-bottom:1.1rem;background:white;border:1px solid var(--tria-line);border-radius:16px;box-shadow:0 8px 24px rgba(38,35,98,.07)}}
        .triacon-header img{{width:205px;height:auto}}
        .triacon-header h1{{color:var(--tria-indigo);font-size:1.75rem;line-height:1.1;margin:0}}
        .triacon-header p{{color:#686484;margin:.35rem 0 0}}
        .dashboard-hero{{display:flex;align-items:center;gap:2rem;background:linear-gradient(120deg,#fff 0%,#f6f4fb 100%);border-left:7px solid var(--tria-red);border-radius:15px;padding:1.5rem 1.8rem;margin:.4rem 0 1.4rem}}
        .dashboard-hero img{{width:240px;max-width:34%}}
        .dashboard-hero span{{color:var(--tria-orange);font-size:.78rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
        .dashboard-hero h2{{color:var(--tria-indigo);margin:.25rem 0;font-size:1.75rem}}
        .dashboard-hero p{{margin:0;color:#686484}}
        .auth-shell{{max-width:620px;margin:4vh auto 1.4rem;text-align:center;background:#fff;border:1px solid var(--tria-line);border-top:6px solid var(--tria-red);border-radius:18px;padding:2rem;box-shadow:0 12px 34px rgba(38,35,98,.09)}}
        .auth-shell img{{width:260px;max-width:75%;margin-bottom:1rem}}
        .auth-shell h1{{margin:.3rem 0}}
        .auth-shell p{{color:#686484}}
        .breadcrumbs{{display:flex;gap:.55rem;align-items:center;color:#77738c;background:#f7f6fb;border:1px solid var(--tria-line);padding:.7rem 1rem;border-radius:10px;margin-bottom:1rem;font-size:.92rem}}
        .breadcrumbs span{{color:var(--tria-orange);font-weight:800}}
        .breadcrumbs strong{{color:var(--tria-indigo)}}
        div[data-testid="stForm"]{{border:1px solid var(--tria-line);border-radius:14px;padding:1.15rem;background:#fff;box-shadow:0 4px 14px rgba(38,35,98,.035)}}
        div[data-testid="stMetric"]{{background:#fff;border:1px solid var(--tria-line);border-top:4px solid var(--tria-orange);border-radius:12px;padding:.85rem 1rem;box-shadow:0 4px 12px rgba(38,35,98,.04)}}
        div[data-testid="stMetricValue"]{{color:var(--tria-indigo)}}
        .stButton button,.stDownloadButton button{{min-height:44px;border-radius:9px;font-weight:700}}
        .stButton button[kind="primary"],.stDownloadButton button[kind="primary"]{{background:var(--tria-red);border-color:var(--tria-red);color:white}}
        .stButton button[kind="primary"]:hover,.stDownloadButton button[kind="primary"]:hover{{background:#d72343;border-color:#d72343}}
        button[data-baseweb="tab"][aria-selected="true"]{{color:var(--tria-red)!important;border-bottom-color:var(--tria-red)!important}}
        button[data-baseweb="tab"]{{color:var(--tria-indigo);font-weight:650}}
        input,textarea,select{{font-size:16px!important}}
        div[data-testid="stToast"]{{background:#e8f7ee!important;border:1px solid #68b684!important;border-left:6px solid #2f9d57!important;color:#174f2a!important}}
        [data-testid="stAlert"]{{border-radius:10px}}
        h1,h2,h3,h4{{color:var(--tria-indigo)}}
        @media(max-width:820px){{.triacon-header{{padding:.85rem 1rem}}.triacon-header img{{width:160px}}.dashboard-hero{{align-items:flex-start;gap:1rem;padding:1.1rem}}.dashboard-hero img{{width:170px}}}}
        @media(max-width:700px){{.block-container{{padding-left:.8rem;padding-right:.8rem}}.stHorizontalBlock{{gap:.5rem}}.triacon-header{{display:block}}.triacon-header img{{margin-bottom:.7rem}}.dashboard-hero{{display:block}}.dashboard-hero img{{max-width:70%;margin-bottom:1rem}}}}
        </style>
        """,
        unsafe_allow_html=True,
    )
    init_db()
    user = authenticated_user()
    if user is None:
        render_auth_page()
        return
    st.markdown(
        f'<header class="triacon-header"><img src="{logo}" alt="TriaCon-logo"><div><h1>Brandveiligheidsinspectie</h1><p>Inspecteren op locatie · rapporteren op kantoor</p></div></header>',
        unsafe_allow_html=True,
    )
    context = hierarchy_selector(user)
    render_breadcrumbs(context)
    choices = load_choices()
    show_flash()
    if not context.get("report"):
        render_dashboard(context)
        return
    project = context["report"]
    tabs = st.tabs(["Dashboard", "Project & complex", "Rapportgegevens", "Algemene gegevens", "Situatie", "Inspectie", "Bevindingen", "Rapport"])
    with tabs[0]: render_dashboard(context)
    with tabs[1]: render_hierarchy_data(context)
    with tabs[2]: render_report_data(project)
    with tabs[3]: render_general_data(project)
    with tabs[4]: render_situation(project)
    with tabs[5]: render_add_finding(project, choices)
    with tabs[6]: render_findings(project)
    with tabs[7]: render_report(project)


if __name__ == "__main__":
    main()

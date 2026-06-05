import argparse
import io
import tempfile
import ubelt as ub
import json
import yaml
import zipfile
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v3, html
from trame.decorators import TrameApp, change
from trame.widgets import markdown

@TrameApp()
class EvaluationCardsApp:
    def __init__(self, path, server=None):
        self.server = get_server(server, client_type="vue3")
        self.state, self.ctrl = self.server.state, self.server.controller

        # Initialize dashboard state
        self.state.cards = []
        self.state.filtered_cards = []
        self.state.selected_card = None
        self.state.search_term = ""
        self.state.result_filter = "All"
        self.state.runs_expanded = True
        self.state.show_python_claim = False
        self.state.current_tab = "runs"
        self.state.upload_show = False
        self.state.upload_msg = ""
        self.state.upload_color = "success"

        self.state.expanded_symbols_runs = []

        # Collect Cards
        self.state.cards = self.find_eval_card_data(path)
        self.state.filtered_cards = self.state.cards.copy()

        unique_orgs = sorted(list(set(c["organization"] for c in self.state.cards)))
        unique_phases = sorted(list(set(c["milestone"] for c in self.state.cards)))
        unique_algos = sorted(list(set(c["algorithm"] for c in self.state.cards)))
        
        # Cool colors for organizations
        org_palette = [
            "teal", "cyan-darken-2", "light-blue-darken-2", 
            "blue-darken-2", "indigo"
        ]
        # Warm/Accent colors for testing phases
        phase_palette = [
            "deep-orange", "purple", "pink", 
            "amber-darken-2", "light-green-darken-2"
        ]
        
        self.state.org_colors = {
            org: org_palette[i % len(org_palette)] 
            for i, org in enumerate(unique_orgs)
        }
        self.state.phase_colors = {
            phase: phase_palette[i % len(phase_palette)] 
            for i, phase in enumerate(unique_phases)
        }

        all_tags = set()
        for c in self.state.cards:
            all_tags.update(c["card"].get("tags", []))
        all_tags.update(unique_orgs)
        all_tags.update(unique_phases)
        all_tags.update(unique_algos)
        self.state.available_tags = sorted(list(all_tags))
        self.state.selected_tags = []


        # Initialize card dependent fields

        results = set(c["result"] for c in self.state.cards)
        self.state.results = ["All"] + sorted(list(results))

        # TODO: Add additional fields as Evaluation Cards become more defined

        self._build_ui()

    def find_eval_card_data(self, root_path="./evaluations-example/"):
        """
        --------------
        Parse suggested algorithm format for run data to build dashboard data structure

        Currently assumes the following structure:

        /PhaseI_DryRun                                  # Milestone name
        └── JHU                                         # Organization
            └── DKPS_PerInstance_Prediction             # Algorithm/approach name
                └── ac0068cf_2026-04-09__15-42-59       # {card_hash}_{timestamp} for each unique card
                    ├── card.yaml                       # Original evalution card YAML definition
                    ├── log                             # Console dump
                    ├── results
                    │   └── f2af6eb66e70                # One subdirectory for each parameter set in the sweep
                    │       └── verdict.json            # Claim result for this parameter set
                    └── verdict.json                    # Aggregate result over all claims

        """
        # TODO: Sync with examples repo as default (no path provided)
        # TODO: Make strict parsing rules
        # TODO: Collapse cards by contents hash and display latest by default
        # TODO: Possibly use MAGNET (e.g. EvaluationCard object) to avoid static parsing
        evaluations_dir = ub.Path(root_path)

        dashboard_contents = []

        for milestone_dir in evaluations_dir.iterdir():
            if not milestone_dir.is_dir():
                continue
            for organization_dir in milestone_dir.iterdir():
                if not organization_dir.is_dir():
                    continue
                for algorithm_dir in organization_dir.iterdir():
                    if not algorithm_dir.is_dir():
                        continue
                    for card_run in algorithm_dir.iterdir():
                        if not card_run.is_dir():
                            continue

                        card_run_details = []

                        card = None
                        claim = None
                        verdict = "VERIFIED"

                        # Parse results
                        if (card_run / "results").exists():
                            for sweep_dir in (card_run / "results").iterdir():
                                result = json.loads(
                                    (sweep_dir / "verdict.json").read_text()
                                )
                                if verdict == "VERIFIED":
                                    verdict = result["status"]
                                    # TODO: verify this behavior
                                result["id"] = sweep_dir.name
                                card_run_details.append(result)
                            card_run_details.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
                        else:
                            print(f"No results directory found in {card_run}")
                            continue

                        # Parse card
                        if (card_run / "card.yaml").exists():
                            with open((card_run / "card.yaml"), "r") as f:
                                card = yaml.safe_load(f)
                                claim_raw = card.get("claim")["python"]
                                split_claim = claim_raw.split(",")
                                # TODO: replace claim with natural language description and hide with code or math button
                                claim = (
                                    "".join(split_claim[:-1])
                                    if len(split_claim) > 1
                                    else split_claim[0]
                                )
                        else:
                            print(f"No card definition found in {card_run}")
                            continue

                        # Parse verdict
                        if (card_run / "verdict.json").exists():
                            with open((card_run / "verdict.json"), "r") as f:
                                verdict_log = json.load(f)
                                verdict = verdict_log["result"]
                                agg_strat = verdict_log["claim_aggregation_strategy"]
                        else:
                            print(f"No verdict found in {card_run}")
                            continue

                        # Parse log.txt
                        log_text = "No log file found."
                        if (card_run / "log").exists():
                            with open((card_run / "log"), "r") as f:
                                log_text = f.read()

                        result_data = {
                            "milestone": milestone_dir.name,
                            "organization": organization_dir.name,
                            "algorithm": algorithm_dir.name,
                            "claim_aggregation_strategy": agg_strat,
                            "card": card,
                            "claim": claim,
                            "result": verdict,
                            "runs": card_run_details,
                            "log": log_text,
                        }
                        result_data["id"], result_data["date"] = (
                            card_run.name.split("_")[0],
                            "".join(card_run.name.split("_")[1:]),
                        )
                        # FIXME: ^this may override same hash cards? for better or worse
                        dashboard_contents.append(result_data)

        return dashboard_contents

    def filter_cards(self, cards, search_term, result, selected_tags):
        """
        Filter cards by search term and category
        """
        filtered = cards

        if search_term:
            search_lower = search_term.lower()
            filtered = [
                c
                for c in filtered
                if search_lower in c["card"]["title"].lower() or ("description" in c["card"] and search_lower in c["card"]["description"].lower())
            ]

        if result != "All":
            filtered = [c for c in filtered if c["result"] == result]

        if selected_tags and len(selected_tags) > 0:
            filtered = [
                c for c in filtered 
                if all(tag in c["card"].get("tags", []) or tag == c["organization"] or tag == c["milestone"] or tag == c["algorithm"] for tag in selected_tags)
            ]
        return filtered

    @change("search_term", "result_filter", "selected_tags")
    def on_filter_change(self, search_term, result_filter, selected_tags, **kwargs):
        self.state.filtered_cards = self.filter_cards(
            self.state.cards, search_term, result_filter, selected_tags
        )
        # 2. Conditionally reset the selected card
        if self.state.selected_card:
            # Check if the currently selected card ID still exists in the filtered results
            is_still_visible = any(c["id"] == self.state.selected_card["id"] for c in self.state.filtered_cards)
            
            if not is_still_visible:
                self.state.selected_card = None

    def find_upload_data(self, root_path="./evaluation_runs/"):
        """
        --------------
        Parse MAGNET output format

        Currently assumes the following structure:

        /ac0068cf_2026-04-09__15-42-59                  # {card_hash}_{timestamp} for each unique card
        ├── card.yaml                                   # Original evalution card YAML definition
        ├── log                                         # Console dump
        ├── results
        │   └── f2af6eb66e70                            # One subdirectory for each parameter set in the sweep
        │       └── verdict.json                        # Claim result for this parameter set
        └── verdict.json                                # Aggregate result over all claims

        """

        card_run = ub.Path(root_path)

        dashboard_contents = []

        milestone = "SelfEvaluation"
        organization = "Local"

        for card_run in card_run.iterdir():
            if not card_run.is_dir():
                continue
            card_run_details = []

            card = None
            claim = None
            verdict = "VERIFIED"

            # Parse results
            if (card_run / "results").exists():
                for sweep_dir in (card_run / "results").iterdir():
                    result = json.loads(
                        (sweep_dir / "verdict.json").read_text()
                    )
                    if verdict == "VERIFIED":
                        verdict = result["status"]
                    result["id"] = sweep_dir.name
                    card_run_details.append(result)
                card_run_details.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
            else:
                print(f"No results directory found in {card_run}")
                continue

            # Parse card
            if (card_run / "card.yaml").exists():
                with open((card_run / "card.yaml"), "r") as f:
                    card = yaml.safe_load(f)
                    claim_raw = card.get("claim")["python"]
                    split_claim = claim_raw.split(",")
                    claim = (
                        "".join(split_claim[:-1])
                        if len(split_claim) > 1
                        else split_claim[0]
                    )
            else:
                print(f"No card definition found in {card_run}")
                continue

            # Parse verdict
            if (card_run / "verdict.json").exists():
                with open((card_run / "verdict.json"), "r") as f:
                    verdict_log = json.load(f)
                    verdict = verdict_log["result"]
                    agg_strat = verdict_log["claim_aggregation_strategy"]
            else:
                print(f"No verdict found in {card_run}")
                continue

            # Parse log
            log_text = "No log file found."
            if (card_run / "log").exists():
                with open((card_run / "log"), "r") as f:
                    log_text = f.read()

            result_data = {
                "milestone": milestone,
                "organization": organization,
                "algorithm": card['title'].replace(" ", "_"),
                "claim_aggregation_strategy": agg_strat,
                "card": card,
                "claim": claim,
                "result": verdict,
                "runs": card_run_details,
                "log": log_text,
            }
            result_data["id"], result_data["date"] = (
                card_run.name.split("_")[0],
                "".join(card_run.name.split("_")[1:]),
            )
            dashboard_contents.append(result_data)

        return dashboard_contents

    @change("uploaded_file")
    def handle_file_upload(self, uploaded_file, **kwargs):
        if not uploaded_file:
            return  # Triggered when the user clears the input

        try:
            # 1. Trame provides the file contents as bytes
            file_bytes = uploaded_file.get("content")
            
            # 2. Create a temporary directory that auto-cleans up
            with tempfile.TemporaryDirectory() as temp_dir:
                
                # 3. Extract the ZIP in memory to the temp directory
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # 4. Parse contents
                new_cards = self.find_upload_data(temp_dir)
                
                if new_cards:
                    self.state.cards = self.state.cards + new_cards
                    
                    # 6. Re-trigger the filter to show the new cards immediately
                    self.state.filtered_cards = self.filter_cards(
                        self.state.cards, 
                        self.state.search_term, 
                        self.state.result_filter, 
                        self.state.selected_tags
                    )
                    
                    # Refresh available tags in the dropdown
                    new_tags = set()
                    for c in new_cards:
                        new_tags.update(c["card"].get("tags", []))

                    unique_orgs = set(c["organization"] for c in new_cards)
                    unique_phases = set(c["milestone"] for c in new_cards)
                    unique_algos = set(c["algorithm"] for c in new_cards)
                    
                    new_tags.update(unique_orgs)
                    new_tags.update(unique_phases)
                    new_tags.update(unique_algos)

                    new_tags.update(self.state.available_tags)
                
                    self.state.available_tags = sorted(list(new_tags))
                    results = set(c["result"] for c in new_cards)
                    results.update(self.state.results)
                    self.state.results = sorted(list(results))
                    self.state.upload_msg = f"Success: Loaded {len(new_cards)} evaluation card(s)."
                    self.state.upload_color = "success"
                    self.state.upload_show = True

                else:
                    self.state.upload_msg = "No valid evaluation cards found in the zip."
                    self.state.upload_color = "warning"
                    self.state.upload_show = True

        except Exception as e:
            self.state.upload_msg = f"Upload failed: {e}"
            self.state.upload_color = "error"
            self.state.upload_show = True
        finally:
            self.state.uploaded_file = None

    def select_card(self, card_id):
        card = next((c for c in self.state.cards if c["id"] == card_id), None)
        self.state.selected_card = card
        self.state.runs_expanded = True
        self.state.show_python_claim = False
        self.state.current_tab = "runs"
        self.state.expanded_symbols_runs = []

    def toggle_symbols(self, run_id=None):        
        expanded = list(self.state.expanded_symbols_runs)
        if run_id in expanded:
            expanded.remove(run_id)
        else:
            expanded.append(run_id)
        self.state.expanded_symbols_runs = expanded

    def clear_filters(self):
        self.state.search_term = ""
        self.state.result_filter = "All"
        self.state.selected_tags = []

    def add_tag_to_filter(self, tag):
            """Appends a clicked tag to the active filter list"""
            # Ensure we have a list to work with
            current_tags = list(self.state.selected_tags) if self.state.selected_tags else []
            
            if tag not in current_tags:
                current_tags.append(tag)
                self.state.selected_tags = current_tags
    def toggle_runs(self):
        self.state.runs_expanded = not self.state.runs_expanded

    def _build_ui(self):
        """
        Dashboard construction
        """
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("MAGNET Visualization - Evaluation Cards Gallery")

            with layout.toolbar:
                v3.VSpacer() # Pushes the input to the far right
                v3.VFileInput(
                    v_model=("uploaded_file", None),
                    accept=".zip",
                    label="Upload Local Run (.zip)",
                    prepend_icon="mdi-folder-zip-outline",
                    variant="solo-filled",
                    density="compact",
                    hide_details=True,
                    clearable=True,
                    flat=True,
                    style="max-width: 300px;" 
                )

            with layout.content:
                with v3.VContainer(fluid=True, classes="pa-6"):
                    # Search and Filter Bar
                    with v3.VRow(classes="mb-4"):
                        with v3.VCol(cols=12, md=6):
                            v3.VTextField(
                                v_model=("search_term",),
                                label="Search cards...",
                                prepend_inner_icon="mdi-magnify",
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(cols=12, md=4):
                            v3.VSelect(
                                v_model=("selected_tags",),
                                items=("available_tags",),
                                label="Filter by Tags",
                                multiple=True,  # Allows selecting multiple tags
                                chips=True,     # Displays selected tags as nice chips inside the box
                                clearable=True, # Adds an 'X' to clear all tags quickly
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(cols=12, md=2):
                            v3.VSelect(
                                v_model=("result_filter",),
                                items=("results",),
                                label="Result",
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )

                    # Main Content Grid
                    with v3.VRow():
                        # Card Gallery (Left Column)
                        with v3.VCol(cols=12, lg=4):
                            html.H2(
                                f"Cards ({{{{ filtered_cards.length }}}})",
                                classes="text-h6 mb-3",
                            )
                            with html.Div(v_if="filtered_cards.length === 0", classes="text-center pa-8 border rounded bg-grey-lighten-4"):
                                v3.VIcon("mdi-text-search", size="large", classes="text-grey mb-3")
                                html.P("No cards match your filters.", classes="text-body-1 text-grey-darken-1 mb-4")
                                v3.VBtn("Clear Filters", color="primary", variant="outlined", click=self.clear_filters)

                            with html.Div(
                                v_else=True,
                                style="max-height: calc(100vh - 300px); overflow-y: auto;"
                            ):
                                with html.Template(
                                    v_for="card in filtered_cards",
                                    __properties=[("key", "card.id")],
                                ):
                                    self._render_card_item()

                        # Card Detail View (Right Column)
                        with v3.VCol(cols=12, lg=8):
                            with html.Div(v_if="selected_card"):
                                self._render_card_detail()

                            with html.Div(v_else=True, classes="text-center pa-12"):
                                v3.VIcon(
                                    "mdi-card-search-outline",
                                    size="x-large",
                                    classes="text-grey-lighten-1 mb-4",
                                )
                                html.P(
                                    "Select a card to view details",
                                    classes="text-h6 text-grey",
                                )
                with v3.VSnackbar(
                    v_model=("upload_show",),
                    timeout=4000,
                    color=("upload_color",),
                    location="bottom right",
                ):
                    html.Span("{{ upload_msg }}", classes="text-body-1 font-weight-medium")
                    with v3.VBtn(
                        color="white", 
                        variant="text", 
                        click="upload_show = False"
                    ):
                        html.Span("Close")

    def _pass_rate_button_context(self):
        return v3.VChip(
            size="small",
            v_bind_color=(
                "card.runs && card.runs.length > 0 ? ("
                "   (card.runs.filter(r => r.status === 'VERIFIED').length / card.runs.length === 1) ? 'success' : "
                "   (card.runs.filter(r => r.status === 'VERIFIED').length / card.runs.length > 0) ? 'warning' : "
                "   'error'"
                ") : 'grey'"
            ),
        )

    def _render_card_item(self):
        with v3.VCard(
            classes="mb-3",
            variant="outlined",
            click=(self.select_card, "[card.id]"),
            style="cursor: pointer; {{ selected_card && selected_card.id === card.id ? 'border: 2px solid #1976d2;' : '' }}",
        ):
            with v3.VCardText():
                with html.Div(classes="d-flex justify-space-between align-start mb-2"):
                    html.Div(
                        "{{ card.card.title }}",
                        classes="text-subtitle-2 font-weight-bold flex-grow-1 mr-3",
                        # Ensure the title itself wraps instead of pushing the boundary
                        style="word-wrap: break-word; white-space: normal;" 
                    )
                    # Wrap the pill in a div that refuses to shrink
                    with html.Div(classes="flex-shrink-0"):
                        with self._pass_rate_button_context():
                            html.Div(
                                "{{ card.runs ? Math.round(card.runs.filter(r => r.status === 'VERIFIED').length / card.runs.length * 100) : 0 }}% Pass"
                            )

                html.P(
                    "{{ card.card.description }}",
                    classes="text-body-2 text-grey-darken-1 mb-2",
                    style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;",
                )

                # --- Structural Metadata Row ---
                with html.Div(classes="d-flex flex-wrap align-center mb-3", style="gap: 4px;"):
                    # Institution
                    v3.VChip(
                        "{{ card.organization }}", 
                        prepend_icon="mdi-domain", 
                        size="small", 
                        v_bind_color="org_colors[card.organization] || 'teal'", 
                        variant="flat",
                        click=(self.add_tag_to_filter, "[card.organization]")
                    )
                    # Testing Phase
                    v3.VChip(
                        "{{ card.milestone }}", 
                        prepend_icon="mdi-flag-triangle", 
                        size="small", 
                        v_bind_color="phase_colors[card.milestone] || 'deep-orange'", 
                        variant="flat",
                        click=(self.add_tag_to_filter, "[card.milestone]")
                    )
                    # Algorithm
                    v3.VChip(
                        "{{ card.algorithm }}", 
                        prepend_icon="mdi-brain", 
                        size="small", 
                        color="blue-grey-darken-1", 
                        variant="flat",
                        click=(self.add_tag_to_filter, "[card.algorithm]")
                    )

                with html.Div(classes="d-flex justify-space-between align-center"):
                    html.Span(
                        "{{ card.runs ? card.runs.length : 0 }} runs",
                        classes="text-caption text-grey",
                    )

    def _render_card_detail(self):
        with v3.VCard(variant="outlined"):
            # Header
            with v3.VCardTitle(classes="pa-6 bg-grey-lighten-4", style="white-space: normal; word-break: break-word;"):
                
                # --- Top Row: Title and Pass Rate Pill ---
                with html.Div(classes="d-flex justify-space-between align-start mb-2"):
                    # Title
                    html.H2(
                        "{{ selected_card.card.title }}", 
                        classes="text-h4 mb-0 flex-grow-1 mr-4",
                        style="white-space: normal; word-break: break-word;"
                    )
                    
                    # Pass Rate Pill (Forced to the right, refusing to shrink)
                    with html.Div(classes="flex-shrink-0"):
                        with v3.VChip(
                            v_bind_color=(
                                "selected_card.runs && selected_card.runs.length > 0 ? ("
                                "   (selected_card.runs.filter(r => r.status === 'VERIFIED').length / selected_card.runs.length === 1) ? 'success' : "
                                "   (selected_card.runs.filter(r => r.status === 'VERIFIED').length > 0) ? 'warning' : "
                                "   'error'"
                                ") : 'grey'"
                            )
                        ):
                            html.Div(
                                "{{ selected_card.runs ? Math.round(selected_card.runs.filter(r => r.status === 'VERIFIED').length / selected_card.runs.length * 100) : 0 }}% Pass"
                            )

                # --- Full Width Content: Description, Author, Tags, Links ---
                html.P(
                    "{{ selected_card.card.description }}",
                    classes="text-body-2 text-grey-darken-2 text-wrap mb-4",
                )
                
                # Line 1: Author
                with html.Div(v_if="selected_card.card.submitter && selected_card.card.submitter.name", classes="mb-3"):
                    v3.VChip(
                        "{{ selected_card.card.submitter.name }}",
                        prepend_icon="mdi-account-circle",
                        color="blue-grey",
                        variant="flat",
                        size="small"
                    )

                # Line 2: Tags
                with html.Div(v_if="selected_card.card.tags && selected_card.card.tags.length > 0", classes="d-flex flex-wrap align-center mb-1", style="gap: 8px;"):
                    with html.Template(v_for="(tag, i) in selected_card.card.tags", __properties=[("key", "i")]):
                        v3.VChip(
                            "{{ tag }}",
                            prepend_icon="mdi-tag-outline",
                            color="grey-darken-2",
                            variant="outlined",
                            size="small",
                            style="height: auto; white-space: normal; padding: 4px 8px;",
                            click=(self.add_tag_to_filter, "[tag]")
                        )

                # DYNAMIC LINKS
                with html.Div(
                    v_if="selected_card.card.links && selected_card.card.links.length > 0", 
                    classes="d-flex flex-wrap mt-3", 
                    style="gap: 8px;"
                ):
                    with html.Template(v_for="(link, i) in selected_card.card.links", __properties=[("key", "i")]):
                        with v3.VBtn(
                            v_bind_href="typeof link === 'string' ? link : link.url",
                            target="_blank",
                            size="small",
                            variant="outlined",
                            color="primary",
                            classes="text-none text-left",
                            style="height: auto; min-height: 32px; padding: 6px 12px; white-space: normal;"
                        ):
                            v3.VIcon(
                                "{{ (typeof link === 'string' ? link : link.url).toLowerCase().includes('github.com') ? 'mdi-github' : "
                                "((typeof link === 'string' ? link : link.url).toLowerCase().includes('huggingface.co') ? 'mdi-robot-outline' : "
                                "(link.type === 'paper' ? 'mdi-file-document-outline' : 'mdi-link')) }}",
                                classes="mr-2"
                            )
                            html.Span(
                                "{{ typeof link === 'string' ? "
                                "(link.toLowerCase().includes('github.com') ? 'GitHub' : (link.toLowerCase().includes('huggingface.co') ? 'Hugging Face' : 'External Link')) "
                                ": (link.title || link.type || 'External Link') }}"
                            )

            v3.VDivider()
            # Claim Section
            with v3.VCardText(classes="pa-6 pb-2"):
                with v3.VCard(
                    elevation=4,
                    rounded=True,
                    classes="pa-4",
                    color="blue-lighten-5",
                    style="border: 2px solid #1976d2;",
                ):
                    # Header with Subtle Icon Toggle Button
                    with html.Div(classes="d-flex align-center justify-space-between mb-4"):
                        with html.Div(classes="d-flex align-center"):
                            v3.VIcon(
                                "mdi-shield-check",
                                classes="mr-3",
                                color="primary",
                                size="x-large",
                            )
                            html.H3(
                                "Claim", classes="text-h6 font-weight-bold text-primary"
                            )
                        
                        # Subtle Python / Math Toggle Button
                        with v3.VBtn(
                            icon=True,
                            click="show_python_claim = !show_python_claim",
                            variant="text",
                            color="primary",
                            size="small",
                        ):
                            v3.VIcon("{{ show_python_claim ? 'mdi-text' : 'mdi-code-braces' }}", size="large")

                    # 1. Theory View (Markdown)
                    with html.Div(
                        v_show="!show_python_claim", 
                        classes="text-body-1 text-grey-darken-3", 
                        # Force extreme word-breaking so nothing spills out of the container
                        style="word-wrap: break-word; overflow-wrap: break-word; white-space: normal; max-width: 100%;"
                    ):
                        # Use property binding (tuple) instead of mustache syntax so Vue handles the reactivity
                        # Note: Depending on your specific trame-markdown version, the prop is usually 'content' or 'source'
                        markdown.Markdown(content=("selected_card.card.description",))

                    # 2. Python Code View
                    with html.Div(v_show="show_python_claim"):
                        v3.VDivider(classes="mb-4", color="primary")
                        
                        # Raw Python Claim
                        html.H4("Assertion Code", classes="text-subtitle-2 font-weight-bold text-grey-darken-1 mb-2")
                        html.Pre(
                            "{{ selected_card.claim }}",
                            classes="text-body-1 mb-4 font-weight-medium text-primary",
                            style="white-space: pre-wrap; word-break: break-word; font-family: 'Fira Code', 'Courier New', monospace; line-height: 2; background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #1976d2;",
                        )

                        # Raw Aggregation Strategy JSON
                        with html.Div(v_if="selected_card.claim_aggregation_strategy", classes="mb-4"):
                            html.H4("Aggregation Strategy", classes="text-subtitle-2 font-weight-bold text-grey-darken-1 mb-2")
                            html.Pre(
                                "\"claim_aggregation_strategy\": {{ JSON.stringify(selected_card.claim_aggregation_strategy, null, 2) }}",
                                classes="text-body-2 mb-0 text-grey-darken-3",
                                style="white-space: pre-wrap; word-break: break-word; font-family: 'Fira Code', 'Courier New', monospace; background: #f5f5f5; padding: 12px; border-radius: 6px; border: 1px solid #e0e0e0;"
                            )

            v3.VDivider(classes="my-6", thickness=2)

            # --- INVESTIGATION WORKSPACE: TABS ---
            with v3.VTabs(v_model=("current_tab",), color="primary", bg_color="grey-lighten-4"):
                v3.VTab(value="runs", text="Sweep Runs", classes="text-none font-weight-bold")
                v3.VTab(value="logs", text="Execution Logs", classes="text-none font-weight-bold")
            
            v3.VDivider()

            # --- TAB CONTENT ---
            with v3.VWindow(v_model=("current_tab",)):
                
                # TAB A: Runs Section
                with v3.VWindowItem(value="runs"):
                    
                    # --- MOVED: AGGREGATION STRATEGY BANNER ---
                    with html.Div(classes="px-6 pt-6 pb-0"):
                        with v3.VAlert(
                            v_if="selected_card.claim_aggregation_strategy",
                            color="blue-grey-lighten-4",
                            variant="flat",
                            density="compact",
                            classes="text-body-2 text-blue-grey-darken-3 d-flex align-center mb-0",
                            prepend_icon="mdi-scale-balance"
                        ):
                            html.Span(
                                "{{ selected_card.claim_aggregation_strategy.type === 'all' ? 'Aggregation Strategy: All sweeps must pass to verify this claim.' : "
                                "(selected_card.claim_aggregation_strategy.type === 'fraction' ? 'Aggregation Strategy: Requires a ' + (selected_card.claim_aggregation_strategy.parameters.threshold * 100) + '% sweep pass rate to verify this claim.' : "
                                "'Aggregation Strategy: ' + selected_card.claim_aggregation_strategy.type) }}"
                            )


                    # Runs List
                    with v3.VCardText(classes="px-6 pb-6 pt-4"):
                        with html.Div(classes="d-flex justify-space-between align-center mb-3"):
                            # Left side: Toggle button
                            with v3.VBtn(
                                click=self.toggle_runs,
                                variant="text",
                                classes="text-none px-0",
                            ):
                                v3.VIcon(
                                    "{{ runs_expanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}",
                                    classes="mr-2",
                                )
                                html.H3("Runs ({{ selected_card.runs.length }})", classes="text-h6 mb-0")

                            # Right side: Run Status Summary Pills
                            with html.Div(classes="d-flex align-center", style="gap: 8px;"):
                                # Success Count Pill
                                with v3.VChip(
                                    v_if="selected_card.runs && selected_card.runs.filter(r => r.status === 'VERIFIED').length > 0",
                                    color="success",
                                    size="small",
                                    variant="flat",
                                    prepend_icon="mdi-check-circle"
                                ):
                                    html.Span("{{ selected_card.runs.filter(r => r.status === 'VERIFIED').length }}")
                                
                                # Failure Count Pill
                                with v3.VChip(
                                    v_if="selected_card.runs && selected_card.runs.filter(r => r.status !== 'VERIFIED').length > 0",
                                    color="error",
                                    size="small",
                                    variant="flat",
                                    prepend_icon="mdi-close-circle"
                                ):
                                    html.Span("{{ selected_card.runs.filter(r => r.status !== 'VERIFIED').length }}")

                        with html.Div(v_if="runs_expanded"):
                            with html.Template(
                                v_for="run in selected_card.runs", __properties=[("key", "run")]
                            ):
                                with v3.VCard(
                                    color="grey-lighten-5",
                                    rounded=True,
                                    elevation=1,
                                    classes="pa-4 mb-4",
                                ):
                                    with html.Div(classes="d-flex justify-space-between align-start mb-2"):
                                        with html.Div(classes="d-flex align-center"):
                                            v3.VIcon(
                                                "{{ run.status === 'VERIFIED' ? 'mdi-check-circle' : 'mdi-close-circle' }}",
                                                v_bind_color="run.status === 'VERIFIED' ? 'success' : 'error'",
                                                classes="mr-2",
                                            )
                                            html.Span("Sweep #{{ run.id }}", classes="text-h6")
                                        
                                        # Status & Timestamp Container
                                        with html.Div(classes="text-right"):
                                            with v3.VChip(
                                                size="small",
                                                v_bind_color=(
                                                    "run.status === 'VERIFIED' ? 'success' : 'error'"
                                                ),
                                                classes="mb-1"
                                            ):
                                                html.Div("{{ run.status }}")
                                            
                                            html.Div(
                                                "{{ run.timestamp ? new Date(run.timestamp).toLocaleString() : 'No timestamp' }}", 
                                                classes="text-caption text-grey"
                                            )
                                            
                                    v3.VProgressLinear(
                                        model_value="100",
                                        v_bind_color="run.status === 'VERIFIED' ? 'success' : 'error'",
                                        height=8,
                                        rounded=True,
                                        classes="mb-4",
                                    )

                                    with html.Div(v_if="run.status !== 'VERIFIED'", classes="mb-3"):
                                        with v3.VAlert(
                                            icon="mdi-message-alert-outline",
                                            type="error",
                                            variant="tonal",
                                            density="compact",
                                            classes="text-body-2 mx-2",
                                        ):
                                            html.Pre(
                                                "{{ run.output }}",
                                                classes="mb-0 text-center",
                                                style="white-space: pre-wrap; word-break: break-word; font-size: 0.875rem;",
                                            )

                                    with v3.VBtn(
                                        click=(self.toggle_symbols, "[run.id]"),
                                        variant="text",
                                        classes="mb-2 text-none px-0",
                                    ):
                                        v3.VIcon(
                                            "{{ expanded_symbols_runs.includes(run.id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}",
                                            classes="mr-2",
                                        )
                                        html.H4("Symbols", classes="text-subtitle-1 font-weight-bold")
                                        
                                    with html.Div(v_if="expanded_symbols_runs.includes(run.id)"):
                                        with html.Template(
                                            v_for="(values, name) in run.symbols",
                                            __properties=[("key", "name")],
                                        ):
                                            with v3.VCard(
                                                color="white",
                                                rounded=True,
                                                elevation=0,
                                                classes="pa-3 mb-2",
                                                style="border-left: 3px solid #1976d2;",
                                            ):
                                                with html.Div(classes="d-flex justify-space-between mb-2"):
                                                    html.Code(
                                                        "{{ name }}",
                                                        classes="text-subtitle-2 font-weight-bold text-primary",
                                                    )
                                                with html.Div(v_if="values !== undefined", classes="text-body-2 mt-1"):
                                                    html.Span("Value: ", classes="font-weight-bold text-grey-darken-2")
                                                    html.Span("{{ values }}", classes="font-family-monospace")
                # TAB B: Logs Section
                with v3.VWindowItem(value="logs"):
                    with v3.VCardText(classes="pa-6"):
                        with html.Div(classes="d-flex align-center mb-4"):
                            v3.VIcon("mdi-console", classes="mr-2 text-grey-darken-2")
                            html.H3("Console Log", classes="text-h6 text-grey-darken-2")
                            
                        with v3.VCard(
                            color="grey-darken-4", 
                            theme="dark", 
                            rounded=True, 
                            classes="pa-4",
                            style="max-height: 600px; overflow-y: auto; border: 1px solid #424242;"
                        ):
                            html.Pre(
                                "{{ selected_card.log }}",
                                classes="text-body-2 mb-0",
                                style="font-family: 'Fira Code', 'Courier New', monospace; color: #a9b7c6; white-space: pre-wrap; word-break: break-all;"
                            )

    def start(self, **kwargs):
        """Start the Trame server"""
        self.server.start(**kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize Evaluation Card Runs")
    parser.add_argument(
        "path", type=str, help="Path to evaluation card results directory"
    )
    args = parser.parse_args()
    app = EvaluationCardsApp(args.path)
    app.start(port=7860, host="0.0.0.0")

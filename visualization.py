import argparse
import ubelt as ub
import json
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v3, html
from trame.decorators import TrameApp, change

@TrameApp()
class EvaluationCardsApp:
    def __init__(self, path=None, server=None):
        self.server = get_server(server, client_type="vue3")
        self.state, self.ctrl = self.server.state, self.server.controller
        
        # Initialize state
        self.state.cards = []
        self.state.filtered_cards = []
        self.state.selected_card = None
        self.state.search_term = ""
        self.state.category_filter = "All"
        self.state.result_filter = "All"
        self.state.runs_expanded = True
        
        # Collect Cards
        self.state.cards = self.find_eval_card_data(path)
        self.state.filtered_cards = self.find_eval_card_data(path)

        # Initialize card dependent fields
        categories = set(c["category"] for c in self.state.cards)
        self.state.categories = ["All"] + sorted(list(categories))

        results = set(c["result"] for c in self.state.cards)
        self.state.results = ["All"] + sorted(list(results))
        
        self.state.symbols_expanded = {c['id']: {r['id']: True} for c in self.state.cards for r in c['runs']}

        self._build_ui()
    
    def find_eval_card_data(self, path="./magnet/cards/evaluations/"):
        """
        Parse local and suggested algorithm format for run data

        Currently assumes the following structure:
        /evaluations
          /card.id
            -results.json
        """
        # TODO: replace with TA1 suggested formatting
        
        evaluation_dir = ub.Path(path)

        results = []

        for card in evaluation_dir.iterdir():
            if card.is_dir():
                results_file = card / 'results.json'
                if results_file.exists():
                    results.append(json.loads(results_file.read_text()))

        return results
    
    def filter_cards(self, cards, search_term, category, result):
        """
        Filter cards by search term and category
        """
        filtered = cards
        
        if search_term:
            search_lower = search_term.lower()
            filtered = [
                c for c in filtered 
                if search_lower in c["title"].lower() or search_lower in c["description"].lower()
            ]
        
        if category != "All":
            filtered = [c for c in filtered if c["category"] == category]
        
        if result != "All":
            filtered = [c for c in filtered if c["result"] == result]
        
        return filtered
    
    @change("search_term", "category_filter", "result_filter")
    def on_filter_change(self, search_term, category_filter, result_filter, **kwargs):
        self.state.filtered_cards = self.filter_cards(
            self.state.cards, 
            search_term, 
            category_filter,
            result_filter
        )
    
    def select_card(self, card_id):
        card = next((c for c in self.state.cards if c["id"] == card_id), None)
        self.state.selected_card = card
        self.state.symbols_expanded = True
        self.state.runs_expanded = True
    
    def toggle_symbols(self, run_id=None):
        self.state.symbols_expanded = not self.state.symbols_expanded

    def toggle_runs(self):
        self.state.runs_expanded = not self.state.runs_expanded
    
    def _build_ui(self):
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("MAGNET Visualization - Evaluation Cards Gallery")
            
            with layout.content:
                with v3.VContainer(fluid=True, classes="pa-6"):
                    # Search and Filter Bar
                    with v3.VRow(classes="mb-4"):
                        with v3.VCol(cols=8):
                            v3.VTextField(
                                v_model=("search_term",),
                                label="Search cards...",
                                prepend_inner_icon="mdi-magnify",
                                variant="outlined",
                                density="compact",
                                hide_details=True
                            )
                        with v3.VCol(cols=2):
                            v3.VSelect(
                                v_model=("category_filter",),
                                items=("categories",),
                                label="Category",
                                variant="outlined",
                                density="compact",
                                hide_details=True
                            )
                        with v3.VCol(cols=2):
                            v3.VSelect(
                                v_model=("result_filter",),
                                items=("results",),
                                label="Result",
                                variant="outlined",
                                density="compact",
                                hide_details=True
                            )
                    
                    # Main Content Grid
                    with v3.VRow():
                        # Card Gallery (Left Column)
                        with v3.VCol(cols=12, lg=4):
                            html.H2(f"Cards ({{{{ filtered_cards.length }}}})", 
                                    classes="text-h6 mb-3")
                            
                            with html.Div(style="max-height: calc(100vh - 300px); overflow-y: auto;"):
                                with html.Template(
                                    v_for="card in filtered_cards",
                                    __properties=[("key", "card.id")]
                                ):
                                    self._render_card_item()
                        
                        # Card Detail View (Right Column)
                        with v3.VCol(cols=12, lg=8):
                            with html.Div(v_if="selected_card"):
                                self._render_card_detail()
                            
                            with html.Div(v_else=True, classes="text-center pa-12"):
                                v3.VIcon("mdi-card-search-outline", size="x-large", 
                                         classes="text-grey-lighten-1 mb-4")
                                html.P("Select a card to view details", 
                                       classes="text-h6 text-grey")
    
    def _pass_rate_button_context(self):
        return v3.VChip(
                        size="small",
                        v_bind_color=(
                            "card.runs && card.runs.length > 0 ? ("
                            "   (card.runs.filter(r => r.status === 'VERIFIED').length / card.runs.length === 1) ? 'success' : "
                            "   (card.runs.filter(r => r.status === 'VERIFIED').length / card.runs.length > 0) ? 'warning' : "
                            "   'error'"
                            ") : 'grey'"
                        ))

    def _render_card_item(self):
        with v3.VCard(
            classes="mb-3",
            variant="outlined",
            click=(self.select_card, "[card.id]"),
            style="cursor: pointer; {{ selected_card && selected_card.id === card.id ? 'border: 2px solid #1976d2;' : '' }}"
        ):
            with v3.VCardText():
                with html.Div(classes="d-flex justify-space-between align-start mb-2"):
                    html.Div("{{ card.title }}", classes="text-subtitle-2 font-weight-bold")
                    with self._pass_rate_button_context():
                        html.Div("{{ card.runs ? Math.round(card.runs.filter(r => r.status === 'VERIFIED').length / card.runs.length * 100) : 0 }}% Pass")
                
                html.P("{{ card.description }}", 
                       classes="text-body-2 text-grey-darken-1 mb-2",
                       style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;")
                
                with html.Div(classes="d-flex justify-space-between align-center"):
                    v3.VChip("{{ card.category }}", size="small", variant="tonal", color="primary")
                    html.Span("{{ card.runs ? card.runs.length : 0 }} runs", 
                              classes="text-caption text-grey")
    
    def _render_card_detail(self):
        with v3.VCard(variant="outlined"):
            # Header
            with v3.VCardTitle(classes="pa-6 bg-grey-lighten-4"):
                with html.Div(classes="d-flex justify-space-between align-start"):
                    with html.Div(classes="flex-grow-1"):
                        html.H2("{{ selected_card.title }}", classes="text-h4 mb-2")
                        html.P("{{ selected_card.description }}", classes="text-body-2 text-grey-darken-2 text-wrap")
                    with html.Div(classes="d-flex align-start ms-4", style="white-space: nowrap;"):
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
                v3.VChip("{{ selected_card.category }}", 
                         color="primary", 
                         variant="tonal",
                         size="small",
                         classes="mt-2")
            
            v3.VDivider()

            # Claim Section
            with v3.VCardText(classes="pa-6 pb-2"):
                with v3.VCard(
                    elevation=4,
                    rounded=True,
                    classes="pa-4",
                    color="blue-lighten-5",
                    style="border: 2px solid #1976d2;"
                ):
                    with html.Div(classes="d-flex align-center mb-4"):
                        v3.VIcon("mdi-shield-check", classes="mr-3", color="primary", size="x-large")
                        html.H3("Claim", classes="text-h6 font-weight-bold text-primary")
                    
                    html.Pre(
                        "{{ selected_card.claim }}", 
                        classes="text-body-1 mb-0 font-weight-medium text-primary",
                        style="white-space: pre-wrap; word-break: break-word; font-family: 'Fira Code', 'Courier New', monospace; line-height: 2; background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #1976d2;"
                    )

            v3.VDivider(classes="my-6", thickness=2)

            # Runs Section
            with v3.VCardText(classes="pa-6"):
                with v3.VBtn(
                    click=self.toggle_runs,
                    variant="text",
                    classes="mb-3 text-none px-0"
                ):
                    v3.VIcon("{{ runs_expanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}", 
                             classes="mr-2")
                    html.H3("Runs ({{ selected_card.runs.length }})", 
                            classes="text-h6")
                
                with html.Div(v_if="runs_expanded"):
                    with html.Template(
                        v_for="run in selected_card.runs",
                        __properties=[("key", "run")]
                    ):
                        with v3.VCard(
                            color="grey-lighten-5",
                            rounded=True,
                            elevation=1,
                            classes="pa-4 mb-4"
                        ):
                            with html.Div(classes="d-flex justify-space-between align-start mb-2"):
                                with html.Div(classes="d-flex align-center"):
                                    v3.VIcon("{{ run.status === 'VERIFIED' ? 'mdi-check-circle' : 'mdi-close-circle' }}",
                                             v_bind_color="run.status === 'VERIFIED' ? 'success' : 'error'",
                                             classes="mr-2")
                                    html.Span("Sweep #{{ run.id }}",
                                              classes="text-h6")
                                with v3.VChip(
                                    size="small",
                                    v_bind_color=(
                                        "run.status === 'VERIFIED' ? 'success' : 'error'"
                                    )):
                                        html.Div("{{ run.status }}")
                            v3.VProgressLinear(
                                model_value="100", # Used as a highlight, could represent in-progress runs?
                                v_bind_color="run.status === 'VERIFIED' ? 'success' : 'error'",
                                height=8,
                                rounded=True,
                                classes="mb-4"
                            )

                            # Failure Message Section
                            with html.Div(v_if="run.status !== 'VERIFIED'", classes="mb-3"):
                                with html.Div():
                                    with v3.VAlert(
                                        icon='mdi-message-alert-outline',
                                        type="error",
                                        variant="tonal",
                                        density="compact",
                                        classes="text-body-2 mx-2"
                                    ):
                                        html.Pre(
                                            "{{ run.output }}",
                                            classes="mb-0 text-center",
                                            style="white-space: pre-wrap; word-break: break-word; font-size: 0.875rem;"
                                        )
                                        
                            # Toggle symbols inside a run
                            with v3.VBtn(
                                click=(self.toggle_symbols),
                                variant="text",
                                classes="mb-2 text-none px-0"
                            ):
                                v3.VIcon(
                                    "{{ symbols_expanded ? 'mdi-code-braces' : 'mdi-chevron-right' }}",
                                    classes="mr-2"
                                )
                                html.H4(
                                    "Symbols",
                                    classes="text-subtitle-1 font-weight-bold"
                                )
                            # Symbols section inside run
                            with html.Div(v_if="symbols_expanded"):
                                with html.Template(
                                    v_for="(values, name) in run.symbols",
                                    __properties=[("key", "name")]
                                ):
                                    with v3.VCard(
                                            color="white",
                                            rounded=True,
                                            elevation=0,
                                            classes="pa-3 mb-2",
                                            style="border-left: 3px solid #1976d2;"
                                        ):
                                            with html.Div(classes="d-flex justify-space-between mb-2"):
                                                html.Code(
                                                    "{{ name }}",
                                                    classes="text-subtitle-2 font-weight-bold text-primary"
                                                )
                                            
                                            with html.Div(
                                                v_if="values !== undefined",
                                                classes="text-body-2 mt-1"
                                            ):
                                                html.Span("Value: ", classes="font-weight-bold text-grey-darken-2")
                                                html.Span("{{ values }}", classes="font-family-monospace")
                
    def start(self, **kwargs):
        """Start the Trame server"""
        self.server.start(**kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize Evaluation Card Runs")
    parser.add_argument('path',
                        type=str,
                        help="Path to evaluation card results directory")
    args = parser.parse_args()
    app = EvaluationCardsApp(args.path)
    app.start()

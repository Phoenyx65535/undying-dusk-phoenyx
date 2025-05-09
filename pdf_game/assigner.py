'''
This module role is to assign page IDs to GameViews,
including reversed & fixed page IDs, and to insert easter-egg pages.
'''
from random import shuffle

from .entities import GameMode, GameView
from .optional_deps import ansi_wrap
from .render import render_filler_page, render_trick

from .mod.campaign import CHECKPOINTS
from .mod.easteregg import insert_eegggv


START_PAGE_ID = 8  # skipping title & 6 pages of disclaimer/tutorial
MAX_FILLER_PAGE = 5


def assign_page_ids(game_views, assign_special_pages=True):
    is_first_assignment = not any(gv.page_id for gv in game_views)
    gv_per_fixed_id = {gv.state.fixed_id: gv for gv in game_views if gv.state and gv.state.fixed_id}
    if any(fixed_id > len(game_views) for fixed_id in gv_per_fixed_id.keys()):
        print(ansi_wrap(f'Not enough GameViews ({len(game_views)}) to assign some of them with fixed IDs: {list(gv_per_fixed_id.keys())}', color='red'))
    attempt = 0
    while True:
        attempt += 1
        if assign_special_pages:
            print(f'Attempt at assigning reversed page ID: {attempt}')
        shuffle(game_views)  # needed to render pages in a random order
        assigner = Assigner(assign_special_pages, gv_per_fixed_id)
        if assigner.attempt(game_views):
            # reverse ID assignation is valid ! => exiting "while" loop
            if is_first_assignment:
                check_all_reachable_views_have_a_page_id(assigner.out_game_views)
            if assign_special_pages and assigner.reversed_id_gv:  # Double-check reverse-ID assignment is OK:
                page_id1 = assigner.reversed_id_gv.src_view.page_id
                page_id2 = assigner.reversed_id_gv.page_id
                assert _reverse_number(page_id2) in range(page_id1 - MAX_FILLER_PAGE, page_id1 + MAX_FILLER_PAGE), f'Wrong reverse IDs: {page_id1} / {page_id2}'
            return assigner.out_game_views

class Assigner:
    def __init__(self, assign_special_pages, gv_per_fixed_id):
        self.assign_special_pages = assign_special_pages
        self.gv_per_fixed_id = dict(gv_per_fixed_id)  # copy so that we can safely reassign values to None
        self.next_page_id, self.out_game_views, self.reversed_id_gv = START_PAGE_ID, [], None

    def attempt(self, game_views):
        for gv in game_views:
            if gv.state and gv.state.reverse_id:
                assert not self.reversed_id_gv, f'Current algorithm cannot handle several GameView asking for a .reverse_id:\n{self.reversed_id_gv}\n{gv}'
                self.reversed_id_gv = gv
                # We need to reset the page ID of the "mirror" GameViews,
                # as some page IDs may have been assign in a previous attempt:
                self.reversed_id_gv.set_page_id(None)
                self.reversed_id_gv.src_view.set_page_id(None)
                break
        try:
            for game_view in game_views:
                if game_view.state and game_view.state.fixed_id:
                    continue

                # Dead-end useful sanity check:
                if game_view.state:
                    action_names = list(game_view.actions.keys())
                    dead_end_ok = game_view.state.last_checkpoint == len(CHECKPOINTS)
                    assert_error_msg = f'Non game-ending dead-end reached: {action_names} - {game_view}'
                    if game_view.state.mode == GameMode.INFO:
                        assert 'SHOW-INFO' in action_names or dead_end_ok, assert_error_msg
                    else:
                        assert action_names not in ([], ['SHOW-INFO']) or dead_end_ok or game_view.state.milestone >= 2, assert_error_msg

                if game_view.prev_page_trick_game_view:
                    trick = game_view.prev_page_trick_game_view.state.trick
                    assert trick
                    trick_game_view = GameView(renderer=_render_trick(game_view.prev_page_trick_game_view))
                    assert trick_game_view.set_page_id(self.next_page_id)
                    self.out_game_views.append(trick_game_view)
                    if self._increment_next_page_id() != 1:
                        # An easter egg was inserted after trick page
                        return False
                    assert trick.filler_pages == 0
                if game_view.state and game_view.state.reverse_id and self.assign_special_pages:
                    src_page_id = game_view.src_view.page_id
                    if not src_page_id or src_page_id >= self.next_page_id or src_page_id < 100:
                        print(f'Reverse ID assignation ABORT - src_page_id={src_page_id} (next_page_id={self.next_page_id})')
                        raise StopIteration  # attempting another reverse ID assignation
                    if game_view.src_view.next_page_trick_game_view:
                        src_page_id += 1 + game_view.src_view.next_page_trick_game_view.state.trick.filler_pages
                    reversed_id = _reverse_number(src_page_id)
                    if reversed_id == src_page_id or reversed_id >= len(game_views) or src_page_id % 10 == 0 or reversed_id < self.next_page_id:
                        print(f'Reverse ID assignation ABORT - reversed_id={reversed_id} (next_page_id={self.next_page_id})')
                        raise StopIteration  # attempting another reverse ID assignation
                    print(f'ID reversal: {src_page_id} -> {reversed_id} (next_page_id={self.next_page_id})')
                    assert game_view.set_page_id(reversed_id)
                else:
                    if game_view.set_page_id(self.next_page_id):
                        self.out_game_views.append(game_view)
                        self._increment_next_page_id()
                    else:  # can happen with the reducer, when trying to assign a page ID,
                           # to a view that already takes its ID from another one
                        assert not self.reversed_id_gv, game_view
                        self.out_game_views.append(game_view)
                if game_view.next_page_trick_game_view:
                    trick = game_view.next_page_trick_game_view.state.trick
                    assert trick
                    assert trick.filler_pages < MAX_FILLER_PAGE, f"{trick.filler_pages=}"
                    for i in range(trick.filler_pages):
                        filler_game_view = GameView(renderer=_render_filler_page(trick, i))
                        assert filler_game_view.set_page_id(self.next_page_id)
                        self.out_game_views.append(filler_game_view)
                        if self._increment_next_page_id() != 1:
                            # An easter egg was inserted inbetween trick filler pages
                            return False
                    trick_game_view = GameView(renderer=_render_trick(game_view.next_page_trick_game_view))
                    assert trick_game_view.set_page_id(self.next_page_id)
                    self.out_game_views.append(trick_game_view)
                    if self._increment_next_page_id() != 1:
                        # An easter egg was inserted before trick page
                        return False
        except StopIteration:
            return False
        return True

    def _increment_next_page_id(self):
        increment = 1
        self.next_page_id += increment
        if self.reversed_id_gv and self.next_page_id == self.reversed_id_gv.page_id:
            assert self.next_page_id not in self.gv_per_fixed_id, 'Conflicting need to use this page ID :('
            self.out_game_views.append(self.reversed_id_gv)
            increment += self._increment_next_page_id()
        gv = self.gv_per_fixed_id.get(self.next_page_id)
        if gv:
            assert gv.set_page_id(self.next_page_id)
            assert gv.state.fixed_id == gv.page_id
            self.out_game_views.append(gv)
            self.gv_per_fixed_id[self.next_page_id] = None
            increment += self._increment_next_page_id()
        if self.assign_special_pages:
            easteregg_game_view = insert_eegggv(self.next_page_id)
            if easteregg_game_view:
                assert easteregg_game_view.set_page_id(self.next_page_id)
                self.out_game_views.append(easteregg_game_view)
                increment += self._increment_next_page_id()
        return increment


def check_all_reachable_views_have_a_page_id(game_views):
    # Sanity check that revealed to be useful, e.g. when a mapscript trigger
    # sets tile overrides on new actions GameViews *AFTER* creating them
    # (instead of adding them on the GameState beforehand).
    for gv in game_views:
        for action, new_gv in gv.actions.items():
            if new_gv:
                assert new_gv.page_id, f'{action} point to a GV with no page ID: {new_gv}'


def _render_trick(trick_game_view):
    # Note: inlining this lambda triggers a justified cell-var-from-loop Pylint warning
    return lambda pdf: render_trick(pdf, trick_game_view)


def _render_filler_page(trick, i):
    filler_renderer = trick.filler_renderer or render_filler_page
    return lambda pdf: filler_renderer(pdf, i)


def _reverse_number(number):
    result = 0
    while number:
        result = result*10 + (number % 10)
        number //= 10
    return result

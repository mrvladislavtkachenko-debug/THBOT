"""FSM states for the bot."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AnalyzeStates(StatesGroup):
    waiting_for_link = State()


class CompareStates(StatesGroup):
    waiting_for_channels = State()

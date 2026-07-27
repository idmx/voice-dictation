"""Unit tests for the state machine."""

import threading

from voice_dictation.core.state import State, StateMachine


class TestStateMachine:
    """Tests for the StateMachine FSM."""

    def test_initial_state_is_idle(self, mock_state_machine: StateMachine) -> None:
        assert mock_state_machine.state == State.IDLE

    def test_transition_idle_to_recording(self, mock_state_machine: StateMachine) -> None:
        assert mock_state_machine.transition(State.RECORDING) is True
        assert mock_state_machine.state == State.RECORDING

    def test_transition_recording_to_transcribing(self, mock_state_machine: StateMachine) -> None:
        mock_state_machine.transition(State.RECORDING)
        assert mock_state_machine.transition(State.TRANSCRIBING) is True
        assert mock_state_machine.state == State.TRANSCRIBING

    def test_transition_transcribing_to_injecting(self, mock_state_machine: StateMachine) -> None:
        mock_state_machine.transition(State.RECORDING)
        mock_state_machine.transition(State.TRANSCRIBING)
        assert mock_state_machine.transition(State.INJECTING) is True
        assert mock_state_machine.state == State.INJECTING

    def test_transition_injecting_to_idle(self, mock_state_machine: StateMachine) -> None:
        mock_state_machine.transition(State.RECORDING)
        mock_state_machine.transition(State.TRANSCRIBING)
        mock_state_machine.transition(State.INJECTING)
        assert mock_state_machine.transition(State.IDLE) is True
        assert mock_state_machine.state == State.IDLE

    def test_forbidden_transition_idle_to_transcribing(
        self, mock_state_machine: StateMachine
    ) -> None:
        assert mock_state_machine.transition(State.TRANSCRIBING) is False
        assert mock_state_machine.state == State.IDLE

    def test_forbidden_transition_recording_to_injecting(
        self, mock_state_machine: StateMachine
    ) -> None:
        mock_state_machine.transition(State.RECORDING)
        assert mock_state_machine.transition(State.INJECTING) is False
        assert mock_state_machine.state == State.RECORDING

    def test_error_returns_to_idle(self, mock_state_machine: StateMachine) -> None:
        mock_state_machine.transition(State.RECORDING)
        mock_state_machine.transition(State.TRANSCRIBING)
        mock_state_machine.force_idle()
        assert mock_state_machine.state == State.IDLE

    def test_state_change_callback(self, mock_state_machine: StateMachine) -> None:
        transitions: list[tuple[State, State]] = []
        mock_state_machine.on_transition(lambda old, new: transitions.append((old, new)))

        mock_state_machine.transition(State.RECORDING)
        mock_state_machine.transition(State.TRANSCRIBING)

        assert len(transitions) == 2
        assert transitions[0] == (State.IDLE, State.RECORDING)
        assert transitions[1] == (State.RECORDING, State.TRANSCRIBING)

    def test_thread_safety(self, mock_state_machine: StateMachine) -> None:
        """Test concurrent transitions don't corrupt state."""
        results: list[bool] = []
        results_lock = threading.Lock()

        def worker() -> None:
            for _ in range(100):
                ok = mock_state_machine.transition(State.RECORDING)
                with results_lock:
                    results.append(ok)
                mock_state_machine.force_idle()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert mock_state_machine.state == State.IDLE
        assert len(results) == 1000

    def test_can_transition(self, mock_state_machine: StateMachine) -> None:
        assert mock_state_machine.can_transition(State.RECORDING) is True
        assert mock_state_machine.can_transition(State.TRANSCRIBING) is False

        mock_state_machine.transition(State.RECORDING)
        assert mock_state_machine.can_transition(State.TRANSCRIBING) is True
        assert mock_state_machine.can_transition(State.IDLE) is True
        assert mock_state_machine.can_transition(State.INJECTING) is False

    def test_double_force_idle(self, mock_state_machine: StateMachine) -> None:
        """force_idle called when already IDLE should not trigger callbacks."""
        transitions: list[tuple[State, State]] = []
        mock_state_machine.on_transition(lambda old, new: transitions.append((old, new)))

        mock_state_machine.force_idle()
        assert len(transitions) == 0
        assert mock_state_machine.state == State.IDLE

    def test_full_pipeline_cycle(self, mock_state_machine: StateMachine) -> None:
        """Test a complete recording -> transcribing -> injecting -> idle cycle."""
        assert mock_state_machine.transition(State.RECORDING) is True
        assert mock_state_machine.transition(State.TRANSCRIBING) is True
        assert mock_state_machine.transition(State.INJECTING) is True
        assert mock_state_machine.transition(State.IDLE) is True
        assert mock_state_machine.state == State.IDLE

    def test_recording_can_return_to_idle(self, mock_state_machine: StateMachine) -> None:
        """Test that RECORDING can transition directly back to IDLE."""
        mock_state_machine.transition(State.RECORDING)
        assert mock_state_machine.transition(State.IDLE) is True
        assert mock_state_machine.state == State.IDLE

    def test_transcribing_can_return_to_idle(self, mock_state_machine: StateMachine) -> None:
        """Test that TRANSCRIBING can transition back to IDLE on error."""
        mock_state_machine.transition(State.RECORDING)
        mock_state_machine.transition(State.TRANSCRIBING)
        assert mock_state_machine.transition(State.IDLE) is True
        assert mock_state_machine.state == State.IDLE

    def test_callback_exception_is_caught(self, mock_state_machine: StateMachine) -> None:
        """Test that exceptions in callbacks don't break the state machine."""

        def bad_callback(old: State, new: State) -> None:
            raise RuntimeError("Callback error")

        mock_state_machine.on_transition(bad_callback)
        assert mock_state_machine.transition(State.RECORDING) is True
        assert mock_state_machine.state == State.RECORDING

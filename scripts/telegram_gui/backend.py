from __future__ import annotations

from . import app as _app

globals().update(
    {
        name: getattr(_app, name)
        for name in dir(_app)
        if name not in {"__builtins__", "__cached__", "__doc__", "__file__", "__loader__", "__name__", "__package__", "__spec__"}
    }
)
del _app

class TelegramGuiBackend:
    def __init__(self, *, action_log_path: Path):
        self.action_log_path = action_log_path
        self.export_mod = export_mod
        self.HUB_URL = HUB_URL
        self.TELEGRAM_WEB_URL = TELEGRAM_WEB_URL
        self.VISIBLE_DIALOGS_SCRIPT = VISIBLE_DIALOGS_SCRIPT
        self.process_runner = ProcessRunner()
        self.run_history = RunHistoryService(TELEGRAM_WORKSPACE_ROOT)
        self.runtime_logger = RuntimeEventLogger(
            events_path=RUNTIME_EVENTS_LOG_FILE,
            errors_path=RUNTIME_ERRORS_LOG_FILE,
        )
        self.gui_run_logger = GuiRunLogger(
            workspace_root=TELEGRAM_WORKSPACE_ROOT,
            runtime_logger=self.runtime_logger,
        )
        self.secret_store = SecretStore(TELEGRAM_WORKSPACE_ROOT / "registry" / "secrets")
        self.preflight_service = PreflightService(workspace_root=TELEGRAM_WORKSPACE_ROOT, default_token=DEFAULT_TOKEN)
        self.portable_profiles = PortableProfileRegistry(
            workspace_root=TELEGRAM_WORKSPACE_ROOT,
            binary_finder=lambda profile_dir: find_portable_telegram_binary(profile_dir),
            logger=self._log_action,
        )
        self.adapters: tuple[TelegramExecutionAdapter, ...] = (
            TdataAdapter(self),
            BridgeAdapter(self),
            CdpAdapter(self),
        )
        self._adapters_by_key = {adapter.key: adapter for adapter in self.adapters}
        self._last_surface_reason = ""
        self._fallback_readiness_cache: dict[tuple[str, str], FallbackReadiness] = {}
        self._security_info_cache: dict[str, dict[str, Any]] = {}
        self._portable_runtime_cache: dict[tuple[str, bool], tuple[float, PortableRuntimeState]] = {}
        self._tdata_helper_lock = threading.Lock()
        self._prune_runtime_artifacts()

    def resolve_profile_dir(self, source_path: str) -> Path:
        return resolve_profile_dir(source_path)

    def normalize_chat_options(self, payload: Any) -> list[ChatOption]:
        return normalize_chat_options(payload)

    def normalize_tdata_chat_options(self, payload: Any) -> list[ChatOption]:
        return normalize_tdata_chat_options(payload)

    def _clean_tab_title(self, value: str) -> str:
        return _clean_tab_title(value)

    def _format_command_error(self, error: Any) -> str:
        return _format_command_error(error)

    def adapter_for_target(self, target: BrowserTarget) -> TelegramExecutionAdapter:
        for adapter in self.adapters:
            if adapter.matches_target(target):
                return adapter
        return self.adapters[-1]

    def surface_badge_for_target(self, target: BrowserTarget | None) -> str:
        if target is None:
            return "Surface pending"
        return self.adapter_for_target(target).badge

    def _preset_choice(self, preset_key: str) -> tuple[str, str]:
        for key, label in RUN_PRESETS:
            if key == preset_key:
                return key, label
        return RUN_PRESETS[0]

    def preset_limits(self, preset_key: str) -> tuple[str, int | None]:
        if preset_key == "quick_check":
            return QUICK_CHECK_HISTORY_LIMIT, QUICK_CHECK_TIMEOUT_SEC
        return "0", None

    def _account_cache_key(self, account: AccountOption | None) -> str:
        if account is None:
            return ""
        return account.key or _normalize_path_key(account.profile_source)

    def _pending_fallback_readiness(self, surface_key: str) -> FallbackReadiness:
        if surface_key == "cdp":
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="pending",
                detail="Проверка CDP surface будет выполнена в фоне или по явному refresh.",
                action_label="Повторить проверку",
            )
        return FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="pending",
            detail="Проверка bridge surface будет выполнена в фоне или по явному refresh.",
            action_label="Повторить проверку",
        )

    def resolve_profile_dir_safe(self, source_path: str) -> tuple[Path | None, str, str]:
        source = str(source_path or "").strip()
        if not source:
            default_profile = DEFAULT_PROFILE_DIR.expanduser()
            if default_profile.exists():
                return (default_profile.resolve(), "ready", f"Используется default profile: {default_profile}")
            return (None, "missing", f"Default profile не найден: {default_profile}")
        candidate = Path(source).expanduser()
        if candidate.is_dir():
            return (candidate.resolve(), "ready", f"Профиль найден: {candidate}")
        if candidate.is_file() and candidate.suffix.lower() == ".zip":
            try:
                return (resolve_profile_dir(source), "ready", f"ZIP profile готов: {candidate}")
            except Exception as exc:
                return (None, "missing", _compact_error_text(str(exc)) or f"Не удалось подготовить ZIP profile: {candidate}")
        if candidate.exists():
            return (None, "missing", f"Путь профиля не является каталогом Telegram: {candidate}")
        return (None, "missing", f"Путь профиля больше не найден: {candidate}")

    def inspect_account_security(self, account: AccountOption | None, *, deep: bool = False) -> dict[str, Any]:
        if account is None:
            return {
                "slot_number": "",
                "token_source": "missing",
                "security_mode": "No token configured",
                "security_state": "blocked",
                "hub_token_status": "pending",
                "hub_token_detail": "Hub token state будет доступен после выбора профиля.",
                "hub_restart_available": False,
            }
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        token_source = account.token_source or _account_token_source(
            token=account.token,
            secret_ref=account.secret_ref,
            slot_token=_slot_token(slot_number),
            default_token=DEFAULT_TOKEN,
        )
        security_mode, security_state = self.preflight_service.security_mode(account.token)
        cache_key = self._account_cache_key(account)
        if deep:
            hub_state = self._inspect_hub_token_state(account.token)
            cached = {
                "slot_number": slot_number,
                "token_source": token_source,
                "security_mode": security_mode,
                "security_state": security_state,
                "hub_token_status": str(hub_state.get("state") or ""),
                "hub_token_detail": str(hub_state.get("detail") or ""),
                "hub_restart_available": bool(hub_state.get("restart_available")),
            }
            if cache_key:
                self._security_info_cache[cache_key] = cached
            return cached
        cached = self._security_info_cache.get(cache_key)
        hub_token_status = "pending"
        hub_token_detail = "Hub token state будет уточнён в фоне или после явного refresh."
        hub_restart_available = False
        if isinstance(cached, dict):
            hub_token_status = str(cached.get("hub_token_status") or hub_token_status)
            hub_token_detail = str(cached.get("hub_token_detail") or hub_token_detail)
            hub_restart_available = bool(cached.get("hub_restart_available"))
        return {
            "slot_number": slot_number,
            "token_source": token_source,
            "security_mode": security_mode,
            "security_state": security_state,
            "hub_token_status": hub_token_status,
            "hub_token_detail": hub_token_detail,
            "hub_restart_available": hub_restart_available,
        }

    def load_portable_profiles(self) -> list[PortableProfileStatus]:
        layout_mod.ensure_workspace(TELEGRAM_WORKSPACE_ROOT, slots=WORKSPACE_SLOTS)
        accounts_dir = TELEGRAM_WORKSPACE_ROOT / "accounts"
        if accounts_dir.exists():
            for slot_dir in sorted((item for item in accounts_dir.iterdir() if item.is_dir()), key=lambda path: path.name):
                slot_number = slot_dir.name
                self.portable_profiles.sync_legacy_slot_profile(slot_number)
        return self.portable_profiles.list_profiles()

    def portable_profile_for_account(self, account: AccountOption | None) -> PortableProfileStatus | None:
        if account is None:
            return None
        profile_dir = str(account.portable_profile_dir or account.profile_source or "").strip()
        if profile_dir:
            status = self.portable_profiles.status(profile_dir)
            if status is not None:
                return status
            resolved_dir, availability_state, availability_detail = self.resolve_profile_dir_safe(profile_dir)
            if availability_state == "missing" and not (account.slot_number or _slot_number_from_source(account.profile_source)):
                return self._missing_portable_profile_status(
                    profile_dir=resolved_dir or Path(profile_dir).expanduser(),
                    label=account.portable_profile_label or account.label,
                    detail=availability_detail,
                )
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        if slot_number:
            return self.portable_profiles.sync_legacy_slot_profile(
                slot_number,
                profile_name=account.portable_profile_name or account.name,
                account_username="",
                account_label=account.portable_profile_label or account.label,
            )
        return None

    def _account_prefers_portable_profile(
        self,
        account: AccountOption | None,
        profile_status: PortableProfileStatus | None,
    ) -> bool:
        if account is None or profile_status is None:
            return False
        profile_key = _normalize_path_key(str(profile_status.profile_dir))
        if _normalize_path_key(account.profile_source) == profile_key:
            return True
        if account.source_kind == "registry" and _normalize_path_key(account.portable_profile_dir) == profile_key:
            return True
        return False

    def _missing_portable_profile_status(self, *, profile_dir: Path, label: str, detail: str) -> PortableProfileStatus:
        root = profile_dir.expanduser()
        source_kind = "managed_folder" if self.portable_profiles._is_under_profiles_root(root) else "adopted_folder"
        managed = source_kind == "managed_folder"
        return PortableProfileStatus(
            profile=PortableProfile(
                profile_id=hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:16],
                profile_name=label or root.name or "portable-profile",
                profile_dir=root,
                binary_path=None,
                portable_dir=root / "TelegramForcePortable",
                tdata_dir=root / "TelegramForcePortable" / "tdata",
                metadata_path=root / "portable-profile.json",
                account_label=label,
                source_kind=source_kind,
                source_path=root,
                managed=managed,
            ),
            running=False,
            pid=None,
            state="missing",
            detail=detail,
        )

    def ensure_account_for_portable_profile(
        self,
        status: PortableProfileStatus,
        *,
        fallback_token: str = "",
        set_default: bool = False,
    ) -> dict[str, str]:
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=str(status.profile_dir))
        token = str(existing.get("token") or "").strip() or str(fallback_token or "").strip() or DEFAULT_TOKEN
        label = status.account_label or status.account_username or status.profile_name
        next_registry = registry_mod.add_or_update_user_by_profile(
            registry,
            name=label,
            token=token,
            profile=str(status.profile_dir),
            secret_ref=str(existing.get("secret_ref") or "").strip(),
            set_default=set_default,
        )
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        row = registry_mod.find_user_by_profile(next_registry, profile=str(status.profile_dir))
        self._log_action(
            f"portable_profile_account_synced profile={status.profile_dir} user={label} running={int(status.running)}"
        )
        return row

    def _registry_secret_in_use(self, registry: dict[str, Any], secret_ref: str) -> bool:
        target = str(secret_ref or "").strip()
        if not target:
            return False
        return any(str(row.get("secret_ref") or "").strip() == target for row in registry_mod.list_users(registry))

    def _delete_registry_secret_if_unused(self, registry: dict[str, Any], secret_ref: str) -> bool:
        ref = str(secret_ref or "").strip()
        if not ref or self._registry_secret_in_use(registry, ref):
            return False
        return self.secret_store.delete_secret(ref) is not None

    def _portable_profile_uses_isolated_runtime(self, profile_status: PortableProfileStatus | None) -> bool:
        if profile_status is None:
            return False
        return not bool(profile_status.profile.slot_number)

    def _portable_profile_runtime_root(self, profile_dir: Path) -> Path:
        return profile_dir / "runtime"

    def _portable_profile_launch_workdir(self, profile_dir: Path) -> Path:
        return self._portable_profile_runtime_root(profile_dir) / "launch_workdir"

    def _portable_profile_launch_tdata(self, profile_dir: Path) -> Path:
        return self._portable_profile_launch_workdir(profile_dir) / "tdata"

    def _portable_profile_helper_workdir(self, profile_dir: Path) -> Path:
        return self._portable_profile_runtime_root(profile_dir) / "helper_workdir"

    def _portable_profile_helper_tdata(self, profile_dir: Path) -> Path:
        return self._portable_profile_helper_workdir(profile_dir) / "tdata"

    def _portable_profile_clone_state_path(self, profile_dir: Path) -> Path:
        return self._portable_profile_runtime_root(profile_dir) / "clone_state.json"

    def _write_portable_profile_runtime_metadata(
        self,
        profile_dir: Path,
        **updates: str,
    ) -> None:
        metadata_path = profile_dir / "portable-profile.json"
        payload = _read_json_file(metadata_path)
        if not payload:
            return
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        if not isinstance(runtime, dict):
            runtime = {}
        for key, value in updates.items():
            runtime[key] = value
        payload["runtime"] = runtime
        payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _write_json_file(metadata_path, payload)

    def _write_portable_profile_clone_state(self, profile_dir: Path, payload: dict[str, Any]) -> None:
        runtime_root = self._portable_profile_runtime_root(profile_dir)
        runtime_root.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(runtime_root, 0o700)
        _write_json_file(self._portable_profile_clone_state_path(profile_dir), payload)

    def _sync_isolated_portable_helper_clone(
        self,
        profile_status: PortableProfileStatus,
        *,
        prefer_launch_clone: bool,
    ) -> None:
        profile_dir = profile_status.profile_dir
        source_tdata = profile_status.profile.tdata_dir
        if not _tdata_dir_looks_valid(source_tdata):
            raise RuntimeError("Канонический TelegramForcePortable/tdata больше не читается.")
        launch_tdata = self._portable_profile_launch_tdata(profile_dir)
        helper_tdata = self._portable_profile_helper_tdata(profile_dir)
        helper_workdir = self._portable_profile_helper_workdir(profile_dir)
        helper_workdir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(helper_workdir, 0o700)
        source_kind = "source_tdata"
        source_dir = source_tdata
        if prefer_launch_clone and _tdata_dir_looks_valid(launch_tdata):
            source_kind = "launch_workdir"
            source_dir = launch_tdata
        _replace_tree(source_dir, helper_tdata)
        synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = {
            "profile_dir": str(profile_dir),
            "source_tdata": str(source_tdata),
            "source_signature": _portable_runtime_signature_from_tdata(source_tdata),
            "launch_workdir": str(self._portable_profile_launch_workdir(profile_dir)),
            "launch_tdata": str(launch_tdata),
            "launch_signature": _portable_runtime_signature_from_tdata(launch_tdata) if _tdata_dir_looks_valid(launch_tdata) else "",
            "helper_workdir": str(helper_workdir),
            "helper_tdata": str(helper_tdata),
            "helper_signature": _portable_runtime_signature_from_tdata(helper_tdata),
            "helper_source": source_kind,
            "helper_synced_at": synced_at,
        }
        self._write_portable_profile_clone_state(profile_dir, payload)
        self._write_portable_profile_runtime_metadata(
            profile_dir,
            launch_workdir=str(self._portable_profile_launch_workdir(profile_dir)),
            helper_workdir=str(helper_workdir),
            helper_source=source_kind,
            helper_last_sync_at=synced_at,
        )

    def _ensure_isolated_portable_helper_clone_seed(self, profile_status: PortableProfileStatus) -> None:
        if not self._portable_profile_uses_isolated_runtime(profile_status):
            return
        helper_tdata = self._portable_profile_helper_tdata(profile_status.profile_dir)
        if _tdata_dir_looks_valid(helper_tdata):
            return
        self._sync_isolated_portable_helper_clone(profile_status, prefer_launch_clone=False)

    def _prepare_isolated_portable_launch_clone(self, profile_status: PortableProfileStatus) -> Path:
        profile_dir = profile_status.profile_dir
        source_tdata = profile_status.profile.tdata_dir
        if not _tdata_dir_looks_valid(source_tdata):
            raise RuntimeError("Не найден канонический TelegramForcePortable/tdata для запуска профиля.")
        launch_workdir = self._portable_profile_launch_workdir(profile_dir)
        launch_tdata = self._portable_profile_launch_tdata(profile_dir)
        source_signature = _portable_runtime_signature_from_tdata(source_tdata)
        launch_signature = _portable_runtime_signature_from_tdata(launch_tdata) if _tdata_dir_looks_valid(launch_tdata) else ""
        if source_signature != launch_signature:
            launch_workdir.mkdir(parents=True, exist_ok=True)
            _chmod_best_effort(launch_workdir, 0o700)
            _replace_tree(source_tdata, launch_tdata)
        self._write_portable_profile_runtime_metadata(
            profile_dir,
            launch_workdir=str(launch_workdir),
        )
        return launch_workdir

    def _isolated_portable_runtime_state(
        self,
        profile_status: PortableProfileStatus,
        *,
        binary_path: Path | None,
    ) -> PortableRuntimeState:
        profile_dir = profile_status.profile_dir
        source_tdata = profile_status.profile.tdata_dir
        launch_workdir = self._portable_profile_launch_workdir(profile_dir)
        launch_tdata = self._portable_profile_launch_tdata(profile_dir)
        helper_workdir = self._portable_profile_helper_workdir(profile_dir)
        helper_tdata = self._portable_profile_helper_tdata(profile_dir)
        clone_state = _read_json_file(self._portable_profile_clone_state_path(profile_dir))
        source_signature = _portable_runtime_signature_from_tdata(source_tdata) if _tdata_dir_looks_valid(source_tdata) else ""
        launch_exists = _tdata_dir_looks_valid(launch_tdata)
        helper_exists = _tdata_dir_looks_valid(helper_tdata)
        launch_signature = _portable_runtime_signature_from_tdata(launch_tdata) if launch_exists else ""
        helper_signature = _portable_runtime_signature_from_tdata(helper_tdata) if helper_exists else ""
        helper_source = str(clone_state.get("helper_source") or "").strip()
        last_sync_at = str(clone_state.get("helper_synced_at") or "").strip()
        helper_matches_launch = bool(launch_exists and helper_exists and helper_signature and helper_signature == launch_signature)
        helper_matches_source = bool(helper_exists and helper_signature and helper_signature == source_signature)
        if not helper_exists:
            state_value = "sync_required"
            detail_value = "Helper-копия ещё не собрана. Закройте профиль и нажмите 'Обновить статус'."
            ready_for_export = False
            needs_rebuild = True
        elif profile_status.running and launch_exists and not helper_matches_launch:
            state_value = "stale"
            detail_value = (
                "Профиль запущен через isolated launch clone. Helper использует последнюю good copy; "
                "после закрытия Telegram нажмите 'Обновить статус' для sync."
            )
            ready_for_export = True
            needs_rebuild = True
        elif profile_status.running:
            state_value = "stale"
            detail_value = (
                "Профиль сейчас запущен. Helper-копия сохранена отдельно, но новый sync разрешён только "
                "после закрытия Telegram и кнопки 'Обновить статус'."
            )
            ready_for_export = True
            needs_rebuild = True
        elif launch_exists and not helper_matches_launch:
            state_value = "sync_required"
            detail_value = "Launch clone остановлена и изменилась. Нажмите 'Обновить статус', чтобы синхронизировать helper-копию."
            ready_for_export = False
            needs_rebuild = True
        elif launch_exists and not launch_signature:
            state_value = "sync_required"
            detail_value = "Launch clone не читается. Пересоберите helper-копию через 'Обновить статус'."
            ready_for_export = False
            needs_rebuild = True
        elif not launch_exists and not helper_matches_source:
            state_value = "sync_required"
            detail_value = "Helper-копия отстаёт от канонического tdata. Нажмите 'Обновить статус' для пересборки."
            ready_for_export = False
            needs_rebuild = True
        elif binary_path is None:
            state_value = "binary_missing"
            detail_value = "Helper-копия готова для helper/export, но binary Telegram не найден."
            ready_for_export = True
            needs_rebuild = False
        else:
            state_value = "ready"
            detail_value = "Helper-копия готова для export; launch работает через отдельный runtime clone."
            ready_for_export = True
            needs_rebuild = False
        return PortableRuntimeState(
            slot_number=profile_status.profile.slot_number,
            state=state_value,
            detail=detail_value,
            source_path=profile_status.profile.source_path or profile_status.profile.profile_dir,
            source_kind=profile_status.profile.source_kind or "profile",
            runtime_dir=helper_tdata,
            tdata_dir=helper_tdata,
            binary_path=binary_path,
            source_signature=source_signature,
            ready_for_export=ready_for_export,
            needs_rebuild=needs_rebuild,
            authorized=False,
            launch_dir=launch_workdir,
            helper_dir=helper_workdir,
            helper_source=helper_source,
            last_sync_at=last_sync_at,
        )

    def inspect_portable_source(self, account: AccountOption | None) -> PortableSourceInfo:
        if account is None:
            return PortableSourceInfo(slot_number="", path=None, kind="missing", detail="Профиль ещё не выбран.")
        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            detail = (
                f"Portable профиль: {profile_status.profile_name} | "
                f"{profile_status.profile_dir}"
            )
            return PortableSourceInfo(
                slot_number=profile_status.profile.slot_number,
                path=profile_status.profile.profile_dir,
                kind=profile_status.profile.source_kind or "profile",
                detail=detail,
                tdata_dir=profile_status.profile.tdata_dir,
            )
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        if not slot_number:
            return PortableSourceInfo(
                slot_number="",
                path=None,
                kind="missing",
                detail="Для portable tdata нужен slot-based профиль из telegram_workspace/accounts/<N>.",
            )
        return detect_slot_portable_source(slot_number=slot_number, profile_source=account.profile_source)

    def inspect_portable_runtime(
        self,
        account: AccountOption | None,
        *,
        probe_auth: bool = False,
        use_cache: bool = True,
    ) -> PortableRuntimeState:
        if account is None:
            return PortableRuntimeState(
                slot_number="",
                state="missing",
                detail="Профиль ещё не выбран.",
            )
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        cache_key = (account.key, bool(probe_auth))
        if use_cache:
            cached = self._portable_runtime_cache.get(cache_key)
            if cached is not None and (time.monotonic() - cached[0]) <= 3.0:
                return cached[1]

        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            binary_path = profile_status.profile.binary_path or find_portable_telegram_binary(profile_status.profile.profile_dir)
            if self._portable_profile_uses_isolated_runtime(profile_status):
                state = self._isolated_portable_runtime_state(
                    profile_status,
                    binary_path=binary_path,
                )
            else:
                state_value = profile_status.state
                detail_value = profile_status.detail
                ready = profile_status.state in {"ready", "running", "binary_missing"}
                state = PortableRuntimeState(
                    slot_number=profile_status.profile.slot_number,
                    state=state_value,
                    detail=detail_value,
                    source_path=profile_status.profile.source_path or profile_status.profile.profile_dir,
                    source_kind=profile_status.profile.source_kind or "profile",
                    runtime_dir=profile_status.profile.tdata_dir,
                    tdata_dir=profile_status.profile.tdata_dir,
                    binary_path=binary_path,
                    source_signature="",
                    ready_for_export=ready,
                    needs_rebuild=False,
                    authorized=False,
                )
            if probe_auth and state.runtime_dir is not None and state.ready_for_export:
                try:
                    self._run_tdata_helper(
                        "list-chats",
                        tdata_dir=state.runtime_dir,
                        extra_args=["--limit", "1"],
                        timeout_sec=min(max(int(TDATA_LIST_TIMEOUT_SEC), 5), 12),
                    )
                except Exception as exc:
                    reason = _classify_failure_reason(str(exc))
                    detail = (
                        "Portable профиль найден, но helper не смог открыть сессию. "
                        "Откройте этот Telegram Desktop профиль и дождитесь полной загрузки."
                    )
                    if reason != "auth/session unreadable":
                        detail = f"{detail} {_compact_error_text(str(exc))}".strip()
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state="unauthorized",
                        detail=detail,
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=False,
                        needs_rebuild=state.needs_rebuild,
                        authorized=False,
                        launch_dir=state.launch_dir,
                        helper_dir=state.helper_dir,
                        helper_source=state.helper_source,
                        last_sync_at=state.last_sync_at,
                    )
                else:
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state=state.state,
                        detail=state.detail,
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=state.ready_for_export,
                        needs_rebuild=state.needs_rebuild,
                        authorized=True,
                        launch_dir=state.launch_dir,
                        helper_dir=state.helper_dir,
                        helper_source=state.helper_source,
                        last_sync_at=state.last_sync_at,
                    )
            now = time.monotonic()
            self._portable_runtime_cache[cache_key] = (now, state)
            if probe_auth:
                self._portable_runtime_cache[(account.key, False)] = (now, state)
            return state

        source_info = self.inspect_portable_source(account)
        profile_dir, availability_state, availability_detail = self.resolve_profile_dir_safe(account.profile_source)
        if profile_dir is None:
            state = PortableRuntimeState(
                slot_number=slot_number,
                state="missing",
                detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                source_path=Path(account.profile_source).expanduser() if account.profile_source else None,
                source_kind=source_info.kind,
                ready_for_export=False,
                authorized=False,
            )
            now = time.monotonic()
            self._portable_runtime_cache[cache_key] = (now, state)
            if probe_auth:
                self._portable_runtime_cache[(account.key, False)] = (now, state)
            return state
        binary_path = find_portable_telegram_binary(profile_dir)
        state = _portable_runtime_state_from_workspace(
            slot_number=slot_number,
            source_info=source_info,
            binary_path=binary_path,
        )
        if probe_auth and state.runtime_dir is not None and state.ready_for_export:
            try:
                self._run_tdata_helper(
                    "list-chats",
                    tdata_dir=state.runtime_dir,
                    extra_args=["--limit", "1"],
                    timeout_sec=min(max(int(TDATA_LIST_TIMEOUT_SEC), 5), 12),
                )
            except Exception as exc:
                reason = _classify_failure_reason(str(exc))
                detail = (
                    "Portable runtime clone не открывается helper'ом. "
                    "Откройте portable Telegram и дождитесь полной загрузки сессии."
                )
                if reason != "auth/session unreadable":
                    detail = f"{detail} {_compact_error_text(str(exc))}".strip()
                state = PortableRuntimeState(
                    slot_number=state.slot_number,
                    state="unauthorized",
                    detail=detail,
                    source_path=state.source_path,
                    source_kind=state.source_kind,
                    runtime_dir=state.runtime_dir,
                    tdata_dir=state.tdata_dir,
                    binary_path=state.binary_path,
                    source_signature=state.source_signature,
                    ready_for_export=False,
                    needs_rebuild=state.needs_rebuild,
                    authorized=False,
                )
            else:
                if state.state == "binary_missing":
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state=state.state,
                        detail=state.detail,
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=True,
                        needs_rebuild=state.needs_rebuild,
                        authorized=True,
                    )
                else:
                    state = PortableRuntimeState(
                        slot_number=state.slot_number,
                        state="ready",
                        detail="Portable runtime clone готова для helper/export.",
                        source_path=state.source_path,
                        source_kind=state.source_kind,
                        runtime_dir=state.runtime_dir,
                        tdata_dir=state.tdata_dir,
                        binary_path=state.binary_path,
                        source_signature=state.source_signature,
                        ready_for_export=True,
                        needs_rebuild=state.needs_rebuild,
                        authorized=True,
                    )
        now = time.monotonic()
        self._portable_runtime_cache[cache_key] = (now, state)
        if probe_auth:
            self._portable_runtime_cache[(account.key, False)] = (now, state)
        return state

    def clear_portable_runtime_cache(self, account: AccountOption | None = None) -> None:
        if account is None:
            self._portable_runtime_cache.clear()
            return
        keys = [key for key in self._portable_runtime_cache if key[0] == account.key]
        for key in keys:
            self._portable_runtime_cache.pop(key, None)

    def prepare_portable_runtime(self, account: AccountOption, *, force: bool = False) -> PortableRuntimeState:
        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            if profile_status is None:
                raise RuntimeError("Portable профиль не найден.")
            if self._portable_profile_uses_isolated_runtime(profile_status):
                if force:
                    if profile_status.running:
                        helper_tdata = self._portable_profile_helper_tdata(profile_status.profile_dir)
                        if _tdata_dir_looks_valid(helper_tdata):
                            self.clear_portable_runtime_cache(account)
                            return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
                        raise RuntimeError(
                            "Профиль сейчас запущен; sync helper-копии запрещён до закрытия Telegram. "
                            "Закройте профиль и повторите 'Обновить статус'."
                        )
                    self._sync_isolated_portable_helper_clone(profile_status, prefer_launch_clone=True)
            self.clear_portable_runtime_cache(account)
            return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        if not slot_number:
            raise RuntimeError("Portable tdata доступен только для slot-based профилей.")
        source_info = self.inspect_portable_source(account)
        if source_info.path is None or (source_info.kind != "zip" and source_info.tdata_dir is None):
            raise RuntimeError(source_info.detail or "Для этого слота нет portable tdata source.")
        runtime_state = self.inspect_portable_runtime(account, probe_auth=False, use_cache=False)
        if not force and runtime_state.state in {"ready", "binary_missing"} and not runtime_state.needs_rebuild:
            _sync_portable_runtime_alias(slot_number)
            return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)

        runtime_root = _slot_runtime_root(slot_number)
        runtime_root.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(runtime_root, 0o700)
        target_dir = runtime_root / "portable_tdata"
        temp_dir = runtime_root / f".portable_tdata_tmp_{_utc_timestamp()}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if source_info.kind == "zip":
            _extract_portable_tdata_zip(source_info.path, temp_dir)
        else:
            shutil.copytree(source_info.tdata_dir, temp_dir)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        temp_dir.replace(target_dir)
        _chmod_best_effort(target_dir, 0o700)
        _sync_portable_runtime_alias(slot_number)
        metadata = {
            "slot_number": slot_number,
            "source_path": str(source_info.path),
            "source_kind": source_info.kind,
            "source_signature": _portable_source_signature(source_info),
            "runtime_dir": str(target_dir),
            "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        self.secret_store.save_registry_file(
            _slot_portable_state_path(slot_number),
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )
        self.clear_portable_runtime_cache(account)
        result = self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
        self._log_action(
            f"portable_runtime_prepared slot={slot_number} state={result.state} source={source_info.kind}:{source_info.path}"
        )
        return result

    def refresh_portable_runtime(self, account: AccountOption) -> PortableRuntimeState:
        return self.prepare_portable_runtime(account, force=True)

    def launch_portable_telegram(self, account: AccountOption) -> str:
        profile_status = self.portable_profile_for_account(account)
        if self._account_prefers_portable_profile(account, profile_status):
            if profile_status is None:
                raise RuntimeError("Portable профиль не найден.")
            latest, already_running = self.launch_portable_profile_dir(str(profile_status.profile_dir))
            label = portable_profile_label(latest)
            if already_running:
                self._log_action(f"portable_profile_already_running profile={latest.profile_dir}")
                return f"Portable профиль уже запущен: {label}."
            return (
                f"Portable профиль запущен: {label}. "
                f"Profile dir: {latest.profile_dir}"
            )
        state = self.prepare_portable_runtime(account, force=False)
        if state.binary_path is None:
            raise RuntimeError(
                "Portable runtime clone подготовлена, но бинарник Telegram не найден. "
                "Проверьте portable-profile.json или путь в ~/Загрузки/Telegram Desktop."
            )
        if state.runtime_dir is None:
            raise RuntimeError("Portable runtime clone ещё не подготовлена.")
        binary_path = state.binary_path
        _sync_portable_runtime_alias(state.slot_number)
        workdir = state.runtime_dir.parent
        try:
            mode = binary_path.stat().st_mode
            if mode & 0o111 == 0:
                binary_path.chmod(mode | 0o755)
        except OSError as exc:
            raise RuntimeError(f"Не удалось подготовить portable binary: {exc}") from exc
        try:
            subprocess.Popen(
                [str(binary_path), "-workdir", str(workdir)],
                cwd=str(binary_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Не удалось запустить portable Telegram: {exc}") from exc
        self._log_action(f"portable_launch binary={binary_path} workdir={workdir}")
        return f"Portable Telegram запущен из {binary_path} с workdir {workdir}."

    def import_portable_profile(
        self,
        source_path: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
        launch: bool = False,
        set_default: bool = False,
    ) -> PortableProfileStatus:
        status = self.portable_profiles.import_zip(
            source_path,
            profile_name=profile_name,
            account_username=account_username,
            account_label=account_label,
            launch=False,
        )
        self._ensure_isolated_portable_helper_clone_seed(status)
        self.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=set_default)
        self.clear_portable_runtime_cache()
        if launch:
            status, _already_running = self.launch_portable_profile_dir(str(status.profile_dir))
        return status

    def adopt_portable_profile(
        self,
        profile_path: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
    ) -> PortableProfileStatus:
        status = self.portable_profiles.adopt_profile(
            profile_path,
            profile_name=profile_name,
            account_username=account_username,
            account_label=account_label,
        )
        self._ensure_isolated_portable_helper_clone_seed(status)
        self.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=False)
        self.clear_portable_runtime_cache()
        return status

    def profile_status(self, profile_dir: str) -> PortableProfileStatus | None:
        return self.portable_profiles.status(profile_dir)

    def launch_portable_profile_dir(self, profile_dir: str) -> tuple[PortableProfileStatus, bool]:
        current = self.portable_profiles.status(profile_dir)
        if current is None:
            raise RuntimeError(f"Portable профиль не найден: {profile_dir}")
        workdir_override: Path | None = None
        if self._portable_profile_uses_isolated_runtime(current):
            workdir_override = self._prepare_isolated_portable_launch_clone(current)
        status, already_running = self.portable_profiles.launch_profile(profile_dir, workdir_override=workdir_override)
        self.ensure_account_for_portable_profile(status, fallback_token=DEFAULT_TOKEN, set_default=False)
        self.clear_portable_runtime_cache()
        return (status, already_running)

    def refresh_portable_profile_dir(self, profile_dir: str) -> PortableRuntimeState:
        status = self.portable_profiles.status(profile_dir)
        if status is None:
            return PortableRuntimeState(
                slot_number="",
                state="missing",
                detail="Portable профиль больше не найден.",
                ready_for_export=False,
                authorized=False,
            )
        if self._portable_profile_uses_isolated_runtime(status):
            if status.running:
                helper_tdata = self._portable_profile_helper_tdata(status.profile_dir)
                if not _tdata_dir_looks_valid(helper_tdata):
                    raise RuntimeError(
                        "Профиль сейчас запущен; helper-копия ещё не собрана. "
                        "Закройте Telegram и повторите 'Обновить статус'."
                    )
            else:
                self._sync_isolated_portable_helper_clone(status, prefer_launch_clone=True)
            self.clear_portable_runtime_cache()
            account = next(
                (item for item in self.load_accounts() if _normalize_path_key(item.profile_source) == _normalize_path_key(str(status.profile_dir))),
                None,
            )
            if account is not None:
                return self.inspect_portable_runtime(account, probe_auth=True, use_cache=False)
            refreshed = self.portable_profiles.status(profile_dir) or status
            return self._isolated_portable_runtime_state(
                refreshed,
                binary_path=refreshed.profile.binary_path or find_portable_telegram_binary(refreshed.profile.profile_dir),
            )
        return PortableRuntimeState(
            slot_number=status.profile.slot_number,
            state=status.state,
            detail=status.detail,
            source_path=status.profile.source_path or status.profile.profile_dir,
            source_kind=status.profile.source_kind or "profile",
            runtime_dir=status.profile.tdata_dir,
            tdata_dir=status.profile.tdata_dir,
            binary_path=status.profile.binary_path,
            ready_for_export=status.state in {"ready", "running", "binary_missing"},
            authorized=False,
        )

    def remove_portable_profile(self, profile_dir: str) -> PortableProfileRemovalResult:
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=profile_dir)
        result = self.portable_profiles.remove_profile(profile_dir)
        next_registry = registry_mod.remove_user_by_profile(registry, profile=profile_dir)
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        secret_removed = self._delete_registry_secret_if_unused(next_registry, str(existing.get("secret_ref") or "").strip())
        self.clear_portable_runtime_cache()
        if existing:
            self._security_info_cache.pop(f"registry:{str(existing.get('name') or '').strip() or _normalize_path_key(profile_dir)}", None)
        self._log_action(
            f"portable_profile_removed profile={profile_dir} kind={result.profile_kind} preserved={int(result.external_data_preserved)}"
        )
        return PortableProfileRemovalResult(
            profile_dir=result.profile_dir,
            profile_label=result.profile_label,
            profile_kind=result.profile_kind,
            removed_paths=result.removed_paths,
            external_data_preserved=result.external_data_preserved,
            secret_removed=secret_removed,
        )

    def import_portable_source(self, source_path: str, *, preferred_slot: str = "") -> dict[str, str]:
        raw_source = Path(str(source_path or "").strip()).expanduser()
        if not raw_source.exists():
            raise RuntimeError(f"Portable source не найден: {raw_source}")
        slot_number = _resolve_import_slot(preferred_slot)
        slot_root = layout_mod.slot_dir(TELEGRAM_WORKSPACE_ROOT, slot_number)
        profile_dir = slot_root / "profile"
        imports_dir = slot_root / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        source_info = detect_import_payload(raw_source)
        if source_info.path is None:
            raise RuntimeError(source_info.detail or "Не удалось распознать portable tdata source.")

        if source_info.kind == "zip":
            for archive in imports_dir.glob("*.zip"):
                try:
                    archive.unlink()
                except OSError:
                    continue
            target = imports_dir / source_info.path.name
            shutil.copy2(source_info.path, target)
            preferred_profile_source = str(profile_dir if _directory_has_payload(profile_dir) else target)
            imported_source = target
        elif source_info.kind == "tdata":
            target = profile_dir / "tdata"
            _replace_tree(source_info.path, target)
            preferred_profile_source = str(profile_dir)
            imported_source = target
        else:
            parent_target = profile_dir / source_info.path.name
            if source_info.tdata_dir == source_info.path / "tdata":
                _replace_tree(source_info.path, parent_target)
                imported_source = parent_target
            else:
                target = profile_dir / "tdata"
                _replace_tree(source_info.tdata_dir, target)
                imported_source = target
            preferred_profile_source = str(profile_dir)
        self.clear_portable_runtime_cache()
        self._log_action(
            f"portable_source_imported slot={slot_number} kind={source_info.kind} source={source_info.path} target={imported_source}"
        )
        return {
            "slot_number": str(slot_number),
            "portable_source": str(imported_source),
            "portable_kind": source_info.kind,
            "preferred_profile_source": preferred_profile_source,
        }

    def probe_bridge_readiness(self, account: AccountOption) -> FallbackReadiness:
        profile_dir = resolve_profile_dir(account.profile_source)
        hub_state = self._inspect_hub_token_state(account.token)
        hub_status = str(hub_state.get("state") or "").strip()
        if hub_status == "foreign_mismatch":
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="foreign_hub",
                detail=str(hub_state.get("detail") or "На :8765 уже живёт внешний hub/process с другим токеном."),
                action_label="Повторить проверку",
            )
        if hub_status == "owned_mismatch":
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="hub_mismatch",
                detail=str(hub_state.get("detail") or "Hub уже запущен этим GUI с другим токеном."),
                action_label="Повторить проверку",
            )
        try:
            target = self._resolve_best_client(account.token, known_client_ids=set(), require_online=True)
        except Exception as exc:
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="client_offline",
                detail=_compact_error_text(str(exc)) or "Bridge-клиент сейчас недоступен.",
                action_label="Повторить проверку",
            )
        if target is not None:
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="ready",
                detail=f"Bridge-клиент готов: {target.client_id} | {target.tab_title or 'Telegram'}",
                target=target,
                action_label="Повторить проверку",
            )
        try:
            browser = _detect_browser_binary()
        except Exception as exc:
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "Не найден совместимый браузер для bridge-profile.",
                action_label="Повторить проверку",
            )
        if Path(browser).name == "google-chrome" and not _profile_has_site_control_extension(profile_dir):
            return FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="extension_setup_required",
                detail=_bridge_manual_setup_detail(profile_dir),
                action_label="Подготовить bridge profile",
            )
        return FallbackReadiness(
            surface_key="bridge",
            surface_label="Telegram Web bridge",
            surface_badge="Fallback Bridge",
            state="client_offline",
            detail=(
                "Bridge-клиент ещё не подключён. Откройте dedicated bridge profile и дождитесь подключения расширения."
            ),
            action_label="Подготовить bridge profile",
        )

    def prepare_bridge_surface(self, account: AccountOption) -> FallbackReadiness:
        readiness = self.probe_bridge_readiness(account)
        if readiness.state in {"ready", "foreign_hub", "hub_mismatch"}:
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=bridge state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        profile_dir = resolve_profile_dir(account.profile_source)
        env = os.environ.copy()
        env["SITECTL_TOKEN"] = account.token
        env["SITECTL_BROWSER_PROFILE"] = str(profile_dir)
        env["SITECTL_START_URL"] = TELEGRAM_WEB_URL
        try:
            run = subprocess.run(
                ["bash", str(START_BROWSER_SCRIPT), "--profile", str(profile_dir), "--url", TELEGRAM_WEB_URL],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=45,
            )
        except Exception as exc:
            readiness = FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "Не удалось запустить bridge profile.",
                action_label="Подготовить bridge profile",
            )
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=bridge state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        launch_output = _mask_known_secrets((run.stdout or "") + "\n" + (run.stderr or ""), [account.token, DEFAULT_TOKEN]).strip()
        if launch_output:
            self._log_action(f"fallback_prepare surface=bridge launcher={_compact_error_text(launch_output)}")
        if run.returncode != 0:
            readiness = FallbackReadiness(
                surface_key="bridge",
                surface_label="Telegram Web bridge",
                surface_badge="Fallback Bridge",
                state="browser_launch_failed",
                detail=_compact_error_text(launch_output) or "Не удалось подготовить bridge profile.",
                action_label="Подготовить bridge profile",
            )
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=bridge state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        deadline = time.time() + 12
        latest = self.probe_bridge_readiness(account)
        while time.time() < deadline and latest.state == "client_offline":
            time.sleep(0.75)
            latest = self.probe_bridge_readiness(account)
        self._cache_fallback_readiness(account, latest)
        self._log_action(f"fallback_prepare surface=bridge state={latest.state} detail={_compact_error_text(latest.detail)}")
        return latest

    def probe_cdp_readiness(self, account: AccountOption, *, deep: bool = False) -> FallbackReadiness:
        profile_dir = resolve_profile_dir(account.profile_source)
        try:
            target = self._ensure_cdp_target(profile_dir, launch_browser=False)
        except Exception as exc:
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "CDP profile сейчас не готов.",
                action_label="Повторить проверку",
            )
        if target is None:
            try:
                _detect_browser_binary()
            except Exception as exc:
                return FallbackReadiness(
                    surface_key="cdp",
                    surface_label="Chrome profile direct",
                    surface_badge="Fallback CDP",
                    state="browser_launch_failed",
                    detail=_compact_error_text(str(exc)) or "Не найден браузер для CDP профиля.",
                    action_label="Повторить проверку",
                )
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="client_offline",
                detail="CDP browser profile ещё не запущен. Нажмите 'Подключить Telegram' или повторите проверку после запуска.",
                action_label="Повторить проверку",
            )
        return self._probe_cdp_target(target, deep=deep)

    def prepare_cdp_surface(self, account: AccountOption) -> FallbackReadiness:
        profile_dir = resolve_profile_dir(account.profile_source)
        try:
            target = self._ensure_cdp_target(profile_dir, launch_browser=True)
        except Exception as exc:
            readiness = FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="browser_launch_failed",
                detail=_compact_error_text(str(exc)) or "Не удалось поднять CDP browser profile.",
                action_label="Повторить проверку",
            )
            self._cache_fallback_readiness(account, readiness)
            self._log_action(f"fallback_prepare surface=cdp state={readiness.state} detail={_compact_error_text(readiness.detail)}")
            return readiness
        readiness = self._probe_cdp_target(target, deep=True)
        self._cache_fallback_readiness(account, readiness)
        self._log_action(f"fallback_prepare surface=cdp state={readiness.state} detail={_compact_error_text(readiness.detail)}")
        return readiness

    def clear_fallback_readiness(self, account: AccountOption | None) -> None:
        if account is None:
            return
        profile_key = _normalize_path_key(account.profile_source)
        for surface_key in ("bridge", "cdp"):
            self._fallback_readiness_cache.pop((surface_key, profile_key), None)

    def _cache_fallback_readiness(self, account: AccountOption, readiness: FallbackReadiness) -> None:
        profile_key = _normalize_path_key(account.profile_source)
        self._fallback_readiness_cache[(readiness.surface_key, profile_key)] = readiness

    def _cached_fallback_readiness(self, account: AccountOption, surface_key: str) -> FallbackReadiness | None:
        return self._fallback_readiness_cache.get((surface_key, _normalize_path_key(account.profile_source)))

    def _probe_cdp_target(self, target: BrowserTarget, *, deep: bool) -> FallbackReadiness:
        port = self._cdp_port_from_target(target)
        if port is None:
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="client_offline",
                detail="CDP target ещё не готов.",
                action_label="Повторить проверку",
            )
        try:
            if deep:
                payload = self._run_cdp_helper(
                    "list-chats",
                    port=port,
                    timeout_sec=10,
                    extra_args=["--url", TELEGRAM_WEB_URL, "--timeout-ms", "8000"],
                )
            else:
                payload = self._run_cdp_helper(
                    "status",
                    port=port,
                    timeout_sec=5,
                    extra_args=["--timeout-ms", "2500"],
                )
        except Exception as exc:
            text = str(exc or "").strip()
            lower = text.lower()
            state = (
                "telegram_auth_required"
                if "не залогинен" in lower or "auth_required" in lower or "not logged into telegram" in lower
                else "client_offline"
            )
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state=state,
                detail=_compact_error_text(text) or "CDP profile ещё не готов.",
                target=target,
                action_label="Повторить проверку",
            )
        if deep and payload.get("auth_required"):
            return FallbackReadiness(
                surface_key="cdp",
                surface_label="Chrome profile direct",
                surface_badge="Fallback CDP",
                state="telegram_auth_required",
                detail="В dedicated CDP profile Telegram ещё не залогинен. Выполните вход и повторите проверку.",
                target=target,
                action_label="Повторить проверку",
            )
        if deep:
            title = self._clean_tab_title(str(payload.get("current_title") or target.tab_title or "Telegram"))
            url = str(payload.get("current_url") or target.tab_url or TELEGRAM_WEB_URL)
        else:
            target_meta = payload.get("telegram_target") or {}
            title = self._clean_tab_title(str(target_meta.get("title") or target.tab_title or "Telegram"))
            url = str(target_meta.get("url") or target.tab_url or TELEGRAM_WEB_URL)
        refreshed = BrowserTarget(client_id=target.client_id, tab_id=target.tab_id, tab_title=title, tab_url=url)
        return FallbackReadiness(
            surface_key="cdp",
            surface_label="Chrome profile direct",
            surface_badge="Fallback CDP",
            state="ready",
            detail=f"CDP profile готов: {refreshed.client_id} | {refreshed.tab_title or 'Telegram'}",
            target=refreshed,
            action_label="Повторить проверку",
        )

    def save_secure_token(self, account: AccountOption, token: str) -> None:
        value = str(token or "").strip()
        if not value:
            raise ValueError("Введите token перед сохранением.")
        if value == DEFAULT_TOKEN:
            raise ValueError("Quickstart token нельзя сохранять как secure token.")
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=account.profile_source)
        secret_ref = str(existing.get("secret_ref") or account.secret_ref or "").strip()
        next_registry = registry_mod.add_or_update_user_by_profile(
            registry,
            name=self._registry_user_name_for_account(account, existing=existing),
            token=value,
            profile=account.profile_source,
            secret_ref=secret_ref,
            set_default=not bool(registry_mod.list_users(registry)),
        )
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        if account.slot_number:
            self.clear_slot_token_file(account.slot_number)
        self._log_action(
            f"secure_token_saved account={account.label} profile={account.profile_source} source=gui token_source=secret_ref"
        )

    def import_slot_token_into_registry(self, account: AccountOption) -> bool:
        slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
        slot_token = _slot_token(slot_number)
        if not slot_number or not slot_token:
            return False
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        existing = registry_mod.find_user_by_profile(registry, profile=account.profile_source)
        if str(existing.get("secret_ref") or "").strip():
            return False
        next_registry = registry_mod.add_or_update_user_by_profile(
            registry,
            name=self._registry_user_name_for_account(account, existing=existing),
            token=slot_token,
            profile=account.profile_source,
            secret_ref=str(existing.get("secret_ref") or "").strip(),
            set_default=not bool(registry_mod.list_users(registry)),
        )
        registry_mod.save_registry(USER_REGISTRY_PATH, next_registry)
        self.clear_slot_token_file(slot_number)
        self._log_action(f"slot_token_imported slot={slot_number} profile={account.profile_source}")
        return True

    def clear_slot_token_file(self, slot_number: str) -> None:
        if not slot_number:
            return
        token_path = TELEGRAM_WORKSPACE_ROOT / "accounts" / slot_number / "keys" / "api_token.txt"
        self.secret_store.save_registry_file(token_path, "")

    def restart_owned_hub_with_token(self, token: str) -> None:
        hub_state = self._inspect_hub_token_state(token)
        if str(hub_state.get("state") or "") != "owned_mismatch":
            raise RuntimeError("Перезапуск hub доступен только для runtime, который поднял этот GUI.")
        self._terminate_owned_runtime("hub")
        self._ensure_hub(token)
        self._log_action("hub_restarted_with_selected_token")

    def _registry_user_name_for_account(self, account: AccountOption, *, existing: dict[str, str] | None = None) -> str:
        existing_row = existing or {}
        name = str(existing_row.get("name") or "").strip()
        if name:
            return name
        for candidate in (account.name, account.label, _auto_profile_label(account.label, account.profile_source)):
            text = str(candidate or "").strip()
            if text:
                return text
        return "Telegram profile"

    def load_last_session(self) -> SessionResumeState | None:
        return self.run_history.load_last_session()

    def load_recent_runs(self, *, limit: int = 20) -> list[RunRecord]:
        return self.run_history.list_recent(limit=limit)

    def build_preflight(
        self,
        *,
        account: AccountOption | None,
        output_path: Path | None,
        preset_key: str,
        connected_target: BrowserTarget | None,
        deep: bool = False,
    ) -> PreflightInfo:
        preset_key, preset_label = self._preset_choice(preset_key)
        notes: list[str] = []
        security_info = self.inspect_account_security(account, deep=deep)
        tdata_ready = False
        helper_python = _selected_helper_python()
        helper_ready = bool(helper_python is not None and TDATA_HELPER_SCRIPT.exists())
        surface_key = "pending"
        surface_label = "Telegram pending"
        surface_badge = "Surface pending"
        surface_reason = "Профиль ещё не выбран."
        is_primary = False
        fallback_bridge: FallbackReadiness | None = None
        fallback_cdp: FallbackReadiness | None = None
        portable_source: PortableSourceInfo | None = None
        portable_runtime: PortableRuntimeState | None = None
        portable_profile: PortableProfileStatus | None = None
        resume_state = self.load_last_session()
        if account is not None:
            profile_dir, resolved_state, resolved_detail = self.resolve_profile_dir_safe(account.profile_source)
            availability_state = str(account.availability_state or "").strip() or "ready"
            availability_detail = str(account.availability_detail or "").strip()
            if resolved_state != "ready":
                availability_state = resolved_state
                if not availability_detail:
                    availability_detail = resolved_detail
            elif not availability_detail:
                availability_detail = resolved_detail
            portable_profile = self.portable_profile_for_account(account)
            if availability_state == "missing":
                slot_number = account.slot_number or _slot_number_from_source(account.profile_source)
                portable_source = PortableSourceInfo(
                    slot_number=slot_number,
                    path=None,
                    kind="missing",
                    detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                )
                portable_runtime = PortableRuntimeState(
                    slot_number=slot_number,
                    state="missing",
                    detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                    ready_for_export=False,
                    authorized=False,
                )
                if portable_profile is None and account.profile_source:
                    portable_profile = self._missing_portable_profile_status(
                        profile_dir=Path(account.profile_source).expanduser(),
                        label=account.portable_profile_label or account.label,
                        detail=availability_detail or "Путь выбранного профиля больше не доступен.",
                    )
                surface_key = "profile_missing"
                surface_label = "Telegram profile missing"
                surface_badge = "Profile missing"
                surface_reason = availability_detail or "Путь выбранного профиля больше не доступен."
                notes.append(surface_reason)
            else:
                portable_source = self.inspect_portable_source(account)
                portable_runtime = self.inspect_portable_runtime(
                    account,
                    probe_auth=bool(deep and helper_ready),
                    use_cache=not deep,
                )
                direct_tdata = resolve_tdata_dir(profile_dir) if profile_dir is not None else None
                if portable_source.path is not None:
                    tdata_ready = bool(helper_ready and portable_runtime.ready_for_export and portable_runtime.runtime_dir is not None)
                else:
                    tdata_ready = direct_tdata is not None and helper_ready
                if deep:
                    fallback_bridge = self.probe_bridge_readiness(account)
                    self._cache_fallback_readiness(account, fallback_bridge)
                    cached_cdp = self._cached_fallback_readiness(account, "cdp")
                    fallback_cdp = cached_cdp or self.probe_cdp_readiness(account)
                    if fallback_cdp is not None:
                        self._cache_fallback_readiness(account, fallback_cdp)
                else:
                    fallback_bridge = self._cached_fallback_readiness(account, "bridge") or self._pending_fallback_readiness("bridge")
                    fallback_cdp = self._cached_fallback_readiness(account, "cdp") or self._pending_fallback_readiness("cdp")
                if connected_target is not None:
                    adapter = self.adapter_for_target(connected_target)
                    surface_key = adapter.key
                    surface_label = adapter.label
                    surface_badge = adapter.badge
                    is_primary = adapter.primary
                    surface_reason = f"Подключено через {adapter.label}."
                elif portable_source is not None and portable_source.path is not None:
                    surface_key = "tdata"
                    surface_label = "Telegram Desktop tdata"
                    surface_badge = "Primary tdata"
                    is_primary = True
                    if tdata_ready:
                        surface_reason = portable_runtime.detail or "Portable runtime clone готова для tdata export."
                    else:
                        surface_reason = portable_runtime.detail or "Portable runtime clone требует подготовки или авторизации."
                elif tdata_ready:
                    surface_key = "tdata"
                    surface_label = "Telegram Desktop tdata"
                    surface_badge = "Primary tdata"
                    is_primary = True
                    surface_reason = "tdata primary surface доступен."
                else:
                    if fallback_bridge.state == "ready":
                        surface_key = fallback_bridge.surface_key
                        surface_label = fallback_bridge.surface_label
                        surface_badge = fallback_bridge.surface_badge
                        surface_reason = f"tdata недоступен; bridge ready. {fallback_bridge.detail}"
                    elif fallback_cdp.state == "ready":
                        surface_key = fallback_cdp.surface_key
                        surface_label = fallback_cdp.surface_label
                        surface_badge = fallback_cdp.surface_badge
                        surface_reason = (
                            f"tdata недоступен; bridge={fallback_bridge.state}. "
                            f"CDP ready. {fallback_cdp.detail}"
                        )
                    else:
                        surface_key = "fallback"
                        surface_label = "Fallback surface"
                        surface_badge = "Fallback required"
                        surface_reason = (
                            f"tdata недоступен; bridge={fallback_bridge.state}, cdp={fallback_cdp.state}. "
                            "Нужна подготовка secondary surface."
                        )
            if preset_key == "resume_last" and resume_state is None:
                notes.append("Resume Last недоступен: нет сохранённой последней сессии.")
            if not helper_ready:
                notes.append("collector helper недоступен: проверьте venv и telegram_tdata_helper.py.")
            if portable_profile is not None:
                notes.append(f"Portable profile: {portable_profile_label(portable_profile)}")
                notes.append(f"Profile dir: {portable_profile.profile_dir}")
            if portable_source is not None and portable_source.path is not None:
                notes.append(f"Portable source: {portable_source.kind} | {portable_source.path}")
                notes.append(f"Portable runtime: {portable_runtime.state}." if portable_runtime is not None else "Portable runtime: pending.")
                if portable_runtime is not None and portable_runtime.state in {"missing", "sync_required"}:
                    notes.append("Helper-копия не синхронизируется автоматически: используйте кнопку 'Обновить статус'.")
                if portable_runtime is not None and portable_runtime.state == "stale":
                    notes.append("Профиль уже запускался через launch clone; после закрытия Telegram нажмите 'Обновить статус'.")
                if portable_runtime is not None and portable_runtime.state == "unauthorized":
                    notes.append("Откройте portable Telegram, чтобы авторизовать runtime clone и дать helper открыть session.")
                if portable_runtime is not None and portable_runtime.state == "binary_missing":
                    notes.append("Portable binary не найден; helper/export доступен, но кнопка запуска будет недоступна.")
            elif tdata_ready:
                notes.append("tdata доступен и будет использован как основной surface.")
            elif account is not None and availability_state != "missing":
                notes.append("tdata не найден; GUI упадёт в fallback adapter.")
                if fallback_bridge is not None:
                    notes.append(f"Bridge: {fallback_bridge.state}.")
                if fallback_cdp is not None:
                    notes.append(f"CDP: {fallback_cdp.state}.")
        history_limit, timeout_sec = self.preset_limits(preset_key)
        if connected_target is not None:
            connection_label = f"Клиент готов: {connected_target.client_id}"
        elif surface_key == "tdata":
            if tdata_ready:
                connection_label = "Primary tdata path готов без hub."
            else:
                connection_label = surface_reason or "Primary tdata path требует подготовки."
        elif fallback_bridge is not None and fallback_bridge.state == "ready" and surface_key == "bridge":
            connection_label = fallback_bridge.detail
        elif fallback_cdp is not None and fallback_cdp.state == "ready" and surface_key == "cdp":
            connection_label = fallback_cdp.detail
        else:
            connection_label = "Hub ещё не подключён."
        hub_reachable = bool(connected_target) or str(security_info.get("hub_token_status") or "") == "ok"
        workspace_health = self.preflight_service.collect_workspace_health(
            runtime_dir=RUNTIME_DIR,
            logs_dir=ACTION_LOG_DIR,
            helper_available=helper_ready,
            collector_python_available=helper_python is not None,
            node_available=bool(shutil.which("node")),
            hub_reachable=hub_reachable if not deep else (
                bool(connected_target) or (self._hub_reachable(account.token) if account is not None else False)
            ),
            stale_runtime_files=self._count_stale_runtime_files(),
            warning=self._foreign_hub_warning(),
        )
        if workspace_health.warning:
            notes.append(workspace_health.warning)
        if workspace_health.stale_runtime_files:
            notes.append(f"Обнаружены stale runtime files: {workspace_health.stale_runtime_files}.")
        self._last_surface_reason = surface_reason
        return self.preflight_service.build(
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            surface_reason=surface_reason,
            is_primary=is_primary,
            tdata_ready=tdata_ready,
            helper_ready=helper_ready,
            output_path=output_path,
            preset_key=preset_key,
            preset_label=preset_label,
            history_limit=history_limit,
            timeout_sec=timeout_sec,
            resume_available=resume_state is not None,
            token=account.token if account is not None else "",
            token_source=str(security_info.get("token_source") or ""),
            workspace_health=workspace_health,
            connection_label=connection_label,
            hub_token_status=str(security_info.get("hub_token_status") or ""),
            hub_token_detail=str(security_info.get("hub_token_detail") or ""),
            hub_restart_available=bool(security_info.get("hub_restart_available")),
            fallback_bridge=fallback_bridge,
            fallback_cdp=fallback_cdp,
            portable_source=portable_source,
            portable_runtime=portable_runtime,
            portable_profile=portable_profile,
            notes=tuple(notes),
        )

    def load_accounts(self) -> list[AccountOption]:
        layout_mod.ensure_workspace(TELEGRAM_WORKSPACE_ROOT, slots=WORKSPACE_SLOTS)
        auto_profiles = _group_auto_profile_sources(layout_mod.list_profiles(TELEGRAM_WORKSPACE_ROOT))
        registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        for auto_name, profile_value in auto_profiles:
            slot_number = _slot_number_from_source(profile_value)
            if slot_number:
                self.portable_profiles.sync_legacy_slot_profile(
                    slot_number,
                    profile_name=_auto_profile_label(auto_name, profile_value),
                    account_label=_auto_profile_label(auto_name, profile_value),
                )
            bootstrap_account = AccountOption(
                key=f"auto:{auto_name}",
                label=_auto_profile_label(auto_name, profile_value),
                name=_auto_profile_label(auto_name, profile_value),
                token="",
                profile_source=profile_value,
                source_kind="auto",
                sort_key=(0, "", ""),
                slot_number=slot_number,
                token_source="slot_key" if slot_number else "missing",
            )
            if slot_number and self.import_slot_token_into_registry(bootstrap_account):
                registry = registry_mod.load_registry(USER_REGISTRY_PATH)
        options: list[AccountOption] = []
        seen_profile_keys: set[str] = set()
        seen_slot_numbers: set[str] = set()

        default_user_name = str(registry.get("default_user") or "").strip()
        for row in registry_mod.list_users(registry):
            name = str(row.get("name") or "").strip()
            token = str(row.get("token") or "").strip() or DEFAULT_TOKEN
            profile_source = str(row.get("profile") or "").strip()
            profile_key = _normalize_path_key(profile_source or str(DEFAULT_PROFILE_DIR))
            seen_profile_keys.add(profile_key)
            rank = 0 if name == default_user_name else 1
            label = name if name else "Пользователь из реестра"
            slot_number = _slot_number_from_source(profile_source)
            if slot_number:
                seen_slot_numbers.add(slot_number)
            options.append(
                AccountOption(
                    key=f"registry:{name or profile_key}",
                    label=label,
                    name=name or label,
                    token=token,
                    profile_source=profile_source,
                    source_kind="registry",
                    sort_key=(rank, label.lower(), profile_key),
                    secret_ref=str(row.get("secret_ref") or "").strip(),
                    slot_number=slot_number,
                    token_source=_account_token_source(
                        token=token,
                        secret_ref=str(row.get("secret_ref") or "").strip(),
                        slot_token=_slot_token(slot_number),
                        default_token=DEFAULT_TOKEN,
                    ),
                )
            )

        for auto_name, profile_value in auto_profiles:
            profile_key = _normalize_path_key(profile_value)
            if profile_key in seen_profile_keys:
                continue
            slot_number = _slot_number_from_source(profile_value)
            if slot_number and slot_number in seen_slot_numbers:
                continue
            slot_token = _slot_token(slot_number)
            token = slot_token or DEFAULT_TOKEN
            label = _auto_profile_label(auto_name, profile_value)
            rank = 2 if slot_number else 3
            options.append(
                AccountOption(
                    key=f"auto:{auto_name}",
                    label=label,
                    name=label,
                    token=token,
                    profile_source=profile_value,
                    source_kind="auto",
                    sort_key=(rank, f"{int(slot_number):04d}" if slot_number else label.lower(), profile_key),
                    slot_number=slot_number,
                    token_source=_account_token_source(
                        token=token,
                        secret_ref="",
                        slot_token=slot_token,
                        default_token=DEFAULT_TOKEN,
                    ),
                )
            )

        enriched: list[AccountOption] = []
        for item in options:
            resolved_profile, availability_state, availability_detail = self.resolve_profile_dir_safe(item.profile_source)
            portable_source = self.inspect_portable_source(item)
            portable_profile = self.portable_profile_for_account(item)
            portable_runtime_state = portable_profile.state if portable_profile is not None else ""
            if not portable_runtime_state and item.slot_number and portable_source.path is not None:
                portable_runtime_state = _portable_runtime_state_from_workspace(
                    slot_number=item.slot_number,
                    source_info=portable_source,
                    binary_path=find_portable_telegram_binary(resolved_profile) if resolved_profile is not None else None,
                ).state
            enriched.append(
                AccountOption(
                    key=item.key,
                    label=item.label,
                    name=item.name,
                    token=item.token,
                    profile_source=item.profile_source,
                    source_kind=item.source_kind,
                    sort_key=item.sort_key,
                    secret_ref=item.secret_ref,
                    slot_number=item.slot_number,
                    token_source=item.token_source,
                    availability_state=availability_state,
                    availability_detail=availability_detail,
                    portable_source_path=str(portable_source.path) if portable_source.path is not None else "",
                    portable_source_kind=portable_source.kind,
                    portable_runtime_state=portable_runtime_state,
                    portable_profile_dir=str(portable_profile.profile_dir) if portable_profile is not None else "",
                    portable_profile_name=portable_profile.profile_name if portable_profile is not None else "",
                    portable_profile_label=(
                        (portable_profile.account_label or portable_profile.account_username)
                        if portable_profile is not None
                        else ""
                    ),
                )
            )

        enriched.sort(key=lambda item: item.sort_key)
        return enriched

    def ensure_connected(self, account: AccountOption, *, launch_browser: bool = True) -> BrowserTarget:
        portable_source = self.inspect_portable_source(account)
        if portable_source.path is not None:
            runtime_state = self.prepare_portable_runtime(account, force=False)
            if runtime_state.ready_for_export and runtime_state.runtime_dir is not None:
                target = BrowserTarget(
                    client_id=f"tdata:{_tdata_target_key(runtime_state.runtime_dir)}",
                    tab_id=0,
                    tab_title="Telegram Desktop",
                    tab_url=str(runtime_state.runtime_dir),
                )
                self._log_action(f"client_ready portable_tdata client_id={target.client_id}")
                return target
            raise PrimarySurfaceBlocked(runtime_state.detail or "Portable tdata недоступен. Откройте portable Telegram.")

        try:
            target = self._adapters_by_key["tdata"].connect(account, launch_browser=False)
        except Exception as exc:
            self._log_action(f"tdata_unavailable reason={_compact_error_text(str(exc))}")
        else:
            if target is not None:
                return target

        bridge_status = self.probe_bridge_readiness(account)
        if bridge_status.state == "ready" and bridge_status.target is not None:
            return bridge_status.target
        if launch_browser and bridge_status.state in {"client_offline", "extension_setup_required"}:
            bridge_status = self.prepare_bridge_surface(account)
            if bridge_status.state == "ready" and bridge_status.target is not None:
                return bridge_status.target
        self._log_action(f"bridge_unavailable reason={bridge_status.state} detail={_compact_error_text(bridge_status.detail)}")

        cdp_status = self.probe_cdp_readiness(account)
        if cdp_status.state == "ready" and cdp_status.target is not None:
            cdp_status = self._probe_cdp_target(cdp_status.target, deep=True)
            if cdp_status.state == "ready" and cdp_status.target is not None:
                return cdp_status.target
        if launch_browser and cdp_status.state in {"client_offline", "telegram_auth_required"}:
            cdp_status = self.prepare_cdp_surface(account)
            if cdp_status.state == "ready" and cdp_status.target is not None:
                return cdp_status.target
        self._log_action(f"cdp_unavailable reason={cdp_status.state} detail={_compact_error_text(cdp_status.detail)}")

        if not launch_browser:
            raise RuntimeError("Нет подключённого клиента Telegram. Нажмите 'Подключить Telegram'.")
        raise RuntimeError(self._fallback_connect_error(bridge_status, cdp_status))

    def fetch_chats(self, account: AccountOption, target: BrowserTarget) -> tuple[BrowserTarget, list[ChatOption]]:
        return self.adapter_for_target(target).list_chats(account, target)

    def open_chat(self, account: AccountOption, target: BrowserTarget, chat: ChatOption) -> BrowserTarget:
        return self.adapter_for_target(target).open_chat(account, target, chat)

    def _tdata_dir_for_account(self, account: AccountOption, *, runtime_error_prefix: str = "runtime_unavailable") -> Path:
        portable_source = self.inspect_portable_source(account)
        if portable_source.path is not None:
            runtime_state = self.prepare_portable_runtime(account, force=False)
            if runtime_state.runtime_dir is None or not runtime_state.ready_for_export:
                detail = runtime_state.detail or "Portable runtime недоступна для этого профиля."
                raise RuntimeError(f"{runtime_error_prefix}: {detail}")
            return runtime_state.runtime_dir

        tdata_dir = resolve_tdata_dir(Path(account.profile_source).expanduser())
        if tdata_dir is None:
            raise RuntimeError(f"{runtime_error_prefix}: Для этого профиля не найден рабочий tdata source.")
        return tdata_dir

    def _resolved_chat_option(self, item: dict[str, Any], *, raw_target: str, source_kind: str) -> ChatOption:
        chat_ref = str(item.get("chat_ref") or item.get("peer_id") or "").strip()
        title = _clean_tab_title(str(item.get("title") or chat_ref or raw_target or "Telegram"))
        username = str(item.get("username") or "").strip()
        subtitle_bits = [str(item.get("subtitle") or "").strip()]
        if username:
            subtitle_bits.append(username)
        subtitle_bits.append("resolved target")
        return ChatOption(
            title=title,
            subtitle=" | ".join(bit for bit in subtitle_bits if bit),
            url=username or raw_target or chat_ref,
            fragment=chat_ref or raw_target,
            peer_id=str(item.get("peer_id") or chat_ref or "").strip(),
            active=False,
            visible=True,
            ordinal=-1,
            source_kind=source_kind,
        )

    def resolve_tdata_chat_target(self, account: AccountOption, chat_target: str) -> ChatOption:
        raw_target = str(chat_target or "").strip()
        if not raw_target:
            raise RuntimeError("not_found: Укажите публичную ссылку Telegram, @username или peer id.")

        if _is_invite_like_target(raw_target):
            payload = self.join_tdata_invite(account, raw_target)
            item = payload.get("item") if isinstance(payload, dict) else None
            if not isinstance(item, dict):
                raise RuntimeError("not_found: Invite path не вернул Telegram chat target.")
            chat = self._resolved_chat_option(item, raw_target=raw_target, source_kind="resolved")
            self._log_action(f"chat_resolved invite account={account.name} chat_ref={chat.fragment}")
            return chat

        normalized = _public_chat_target_from_value(raw_target)
        if not normalized:
            raise RuntimeError(f"not_found: Неподдерживаемый публичный target Telegram: {raw_target}")

        tdata_dir = self._tdata_dir_for_account(account)
        payload = self._run_tdata_helper(
            "resolve-chat",
            tdata_dir=tdata_dir,
            extra_args=["--chat", raw_target],
            timeout_sec=_tdata_helper_timeout_seconds("resolve-chat"),
        )
        access_state = str(payload.get("access_state") or "not_found").strip() if isinstance(payload, dict) else "not_found"
        detail = str(payload.get("detail") or "").strip() if isinstance(payload, dict) else ""
        if not isinstance(payload, dict) or not bool(payload.get("ok")) or access_state != "ok":
            message = detail or {
                "not_found": "Target не найден этим профилем.",
                "invite_required": "Этот target требует invite/join path.",
                "resolved_but_no_access": "Target резолвится, но текущий профиль не имеет доступа к истории.",
                "runtime_unavailable": "Portable runtime недоступна.",
            }.get(access_state, "Не удалось подготовить target для экспорта.")
            raise RuntimeError(f"{access_state}: {message}")
        item = payload.get("item")
        if not isinstance(item, dict):
            raise RuntimeError("not_found: resolve-chat не вернул Telegram chat target.")
        chat = self._resolved_chat_option(item, raw_target=normalized, source_kind="resolved")
        self._log_action(f"chat_resolved public account={account.name} chat_ref={chat.fragment}")
        return chat

    def join_tdata_invite(self, account: AccountOption, invite_link: str) -> dict[str, Any]:
        tdata_dir = self._tdata_dir_for_account(account)
        payload = self._run_tdata_helper(
            "join-invite",
            tdata_dir=tdata_dir,
            extra_args=["--invite-link", invite_link],
            timeout_sec=_tdata_helper_timeout_seconds("join-invite"),
        )
        item = payload.get("item") if isinstance(payload, dict) else None
        title = str(item.get("title") or "") if isinstance(item, dict) else ""
        peer_id = str(item.get("peer_id") or "") if isinstance(item, dict) else ""
        self._log_action(
            f"invite_joined account={account.name} title={_compact_error_text(title)} peer_id={peer_id or '-'}"
        )
        return payload

    def _fallback_connect_error(self, bridge_status: FallbackReadiness, cdp_status: FallbackReadiness) -> str:
        if bridge_status.state == "extension_setup_required":
            if cdp_status.state == "ready":
                return cdp_status.detail
            if cdp_status.state == "telegram_auth_required":
                return (
                    f"{bridge_status.detail} "
                    "CDP profile открыт, но Telegram там ещё не залогинен. Выполните вход и повторите подключение."
                )
            return bridge_status.detail
        if bridge_status.state in {"foreign_hub", "hub_mismatch"}:
            if cdp_status.state == "ready":
                return cdp_status.detail
            return bridge_status.detail
        if cdp_status.state == "telegram_auth_required":
            return cdp_status.detail
        if cdp_status.state == "browser_launch_failed":
            return cdp_status.detail
        details = [detail for detail in (bridge_status.detail, cdp_status.detail) if detail]
        return details[0] if details else "Не удалось подключить Telegram Web через выбранный профиль."

    def run_export(
        self,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        *,
        preset_key: str = "full_history",
        operation_kind: str = "usernames",
    ) -> ExportResult:
        ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc)
        run_id = _utc_timestamp()
        operation_kind = normalize_operation_kind(operation_kind)
        self._log_action(f"run_start output={output_path} chat={chat.url} client_id={target.client_id}")
        preset_key, preset_label = self._preset_choice(preset_key)
        adapter = self.adapter_for_target(target)
        self.gui_run_logger.append_run_event(
            run_id,
            event="run_start",
            profile=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            status="running",
            message=f"{preset_label} started",
            details={
                "operation_kind": operation_kind,
                "surface_key": adapter.key,
                "surface_label": adapter.label,
                "output_path": str(output_path),
            },
        )
        try:
            if operation_kind == "public_phones":
                if not self._is_tdata_target(target):
                    raise RuntimeError("Сбор открытых номеров v1 доступен только для Primary tdata.")
                tdata_dir = self._tdata_dir_from_target(target)
                if tdata_dir is None:
                    raise RuntimeError("tdata target is invalid.")
                result = self._run_public_phone_export_via_tdata(
                    tdata_dir=tdata_dir,
                    chat=chat,
                    output_path=output_path,
                    emit=emit,
                    controller=controller,
                    preset_key=preset_key,
                    preset_label=preset_label,
                    surface_key=adapter.key,
                    surface_label=adapter.label,
                    surface_badge=adapter.badge,
                )
            else:
                result = adapter.run_export(
                    account,
                    target,
                    chat,
                    output_path,
                    emit,
                    controller=controller,
                    preset_key=preset_key,
                    preset_label=preset_label,
                )
        except Exception as exc:
            self._log_action(f"run_failed error={type(exc).__name__} message={_compact_error_text(str(exc))}")
            self._record_failed_run(
                run_id=run_id,
                account=account,
                chat=chat,
                output_path=output_path,
                preset_key=preset_key,
                preset_label=preset_label,
                surface_key=adapter.key,
                surface_label=adapter.label,
                surface_badge=adapter.badge,
                started_at=started_at,
                failure_reason=_classify_failure_reason(str(exc)),
                operation_kind=operation_kind,
            )
            self.runtime_logger.log_exception(
                component="telegram_gui",
                event="run_failed",
                exc=exc,
                run_id=run_id,
                profile=account.label,
                chat_ref=chat.fragment,
                chat_title=chat.title,
                message=f"{preset_label} failed",
                details={
                    "operation_kind": operation_kind,
                    "surface_key": adapter.key,
                    "surface_label": adapter.label,
                    "output_path": str(output_path),
                },
            )
            raise
        finished_at = datetime.now(timezone.utc)
        duration_sec = max(int((finished_at - started_at).total_seconds()), 0)
        if not result.started_at:
            result = ExportResult(
                **{
                    **result.__dict__,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_sec": duration_sec,
                    "status": result.status or ("partial" if result.interrupted else "done"),
                    "security_mode": result.security_mode or self.preflight_service.security_mode(account.token)[0],
                    "operation_kind": normalize_operation_kind(result.operation_kind or operation_kind),
                }
            )
        result = self._record_run(
            run_id=run_id,
            account=account,
            chat=chat,
            result=result,
            preset_key=preset_key,
            preset_label=preset_label,
        )
        self.gui_run_logger.append_run_event(
            run_id,
            event="run_finished",
            profile=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            status=result.status or ("partial" if result.interrupted else "done"),
            message=f"{preset_label} finished",
            details={
                "operation_kind": result.operation_kind,
                "history_messages_scanned": result.history_messages_scanned,
                "usernames_found": result.usernames_found,
                "phones_found": result.phones_found,
                "safe_count": result.safe_count,
                "interrupted": result.interrupted,
                "output_path": str(result.output_path),
            },
        )
        return result

    def _record_run(
        self,
        *,
        run_id: str = "",
        account: AccountOption,
        chat: ChatOption,
        result: ExportResult,
        preset_key: str,
        preset_label: str,
    ) -> ExportResult:
        self.run_history.ensure()
        created_at = run_id or _utc_timestamp()
        run_id = created_at
        surface_key = result.surface_key or "unknown"
        surface_label = result.surface_label or surface_key
        surface_badge = result.surface_badge or surface_label
        summary_path = self.run_history.run_summary_path(run_id)
        artifacts_path = self.run_history.run_artifacts_path(run_id)
        events_path = self.run_history.run_events_path(run_id)
        operation_kind = normalize_operation_kind(result.operation_kind)
        result = ExportResult(
            **{
                **result.__dict__,
                "operation_kind": operation_kind,
                "summary_path": summary_path,
                "artifacts_path": artifacts_path,
                "events_path": events_path,
            }
        )
        artifacts = build_artifact_bundle(result)
        record = RunRecord(
            run_id=run_id,
            created_at=created_at,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            account_key=account.key,
            account_label=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            output_path=result.output_path,
            interrupted=result.interrupted,
            safe_count=result.safe_count,
            usernames_found=result.usernames_found,
            history_messages_scanned=result.history_messages_scanned,
            operation_kind=operation_kind,
            phones_found=result.phones_found,
            private_phones_found=result.private_phones_found,
            status=result.status or ("partial" if result.interrupted else "done"),
            duration_sec=result.duration_sec,
            started_at=result.started_at,
            finished_at=result.finished_at,
            security_mode=result.security_mode,
            failure_reason=result.failure_reason,
            artifacts=artifacts,
        )
        session = SessionResumeState(
            account_key=account.key,
            account_label=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            output_path=result.output_path,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            created_at=created_at,
            operation_kind=operation_kind,
            last_surface_reason=self._last_surface_reason,
            last_output_dir=result.output_path.parent,
            last_status=result.status or ("partial" if result.interrupted else "done"),
        )
        self.run_history.append_run(record)
        self.run_history.write_run_summary(record)
        self.run_history.write_run_artifacts(record)
        self.run_history.save_last_session(session)
        append_index_entry(
            index_path=ARTIFACT_INDEX_PATH,
            created_at=created_at,
            account_label=account.label,
            chat_title=chat.title,
            chat_ref=chat.fragment,
            preset_label=preset_label,
            surface_badge=surface_badge,
            status=record.status,
            artifacts=artifacts,
        )
        return result

    def _record_failed_run(
        self,
        *,
        run_id: str = "",
        account: AccountOption,
        chat: ChatOption,
        output_path: Path,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
        started_at: datetime,
        failure_reason: str,
        operation_kind: str,
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        created_at = run_id or _utc_timestamp()
        run_id = created_at
        duration_sec = max(int((finished_at - started_at).total_seconds()), 0)
        summary_path = self.run_history.run_summary_path(run_id)
        artifacts_path = self.run_history.run_artifacts_path(run_id)
        events_path = self.run_history.run_events_path(run_id)
        operation_kind = normalize_operation_kind(operation_kind)
        usernames_txt = None
        phones_txt = None
        phones_json = None
        private_phones_txt = None
        private_phones_json = None
        if operation_kind == "public_phones":
            phones_txt = output_path.with_suffix(".txt")
            phones_json = output_path.with_suffix(".json")
            private_phones_txt = output_path.with_suffix(".private.txt")
            private_phones_json = output_path.with_suffix(".private.json")
        else:
            usernames_txt = output_path.with_name(f"{output_path.stem}_usernames.txt")
        record = RunRecord(
            run_id=run_id,
            created_at=created_at,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            account_key=account.key,
            account_label=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            output_path=output_path,
            interrupted=False,
            safe_count=0,
            usernames_found=0,
            history_messages_scanned=0,
            operation_kind=operation_kind,
            phones_found=0,
            private_phones_found=0,
            status="failed",
            duration_sec=duration_sec,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            security_mode=self.preflight_service.security_mode(account.token)[0],
            failure_reason=failure_reason,
            artifacts=ArtifactBundle(
                markdown=output_path,
                usernames_txt=usernames_txt,
                phones_txt=phones_txt,
                phones_json=phones_json,
                private_phones_txt=private_phones_txt,
                private_phones_json=private_phones_json,
                summary_json=summary_path,
                artifacts_json=artifacts_path,
                events_jsonl=events_path,
            ),
        )
        self.run_history.append_run(record)
        self.run_history.write_run_summary(record)
        self.run_history.write_run_artifacts(record)
        self.gui_run_logger.append_run_event(
            run_id,
            event="run_failed",
            profile=account.label,
            chat_ref=chat.fragment,
            chat_title=chat.title,
            status="failed",
            level="error",
            message=f"{preset_label} failed",
            details={
                "operation_kind": operation_kind,
                "surface_key": surface_key,
                "surface_label": surface_label,
                "failure_reason": failure_reason,
                "output_path": str(output_path),
            },
        )

    def _ensure_cdp_target(self, profile_dir: Path, *, launch_browser: bool) -> BrowserTarget | None:
        port = self._find_active_cdp_port(profile_dir)
        if port is None and not launch_browser:
            return None
        if port is None:
            port = self._launch_cdp_browser(profile_dir)
        payload = self._run_cdp_helper(
            "status",
            port=port,
            timeout_sec=15,
            extra_args=["--timeout-ms", "15000"],
        )
        target_meta = payload.get("telegram_target") or {}
        tab_url = str(target_meta.get("url") or TELEGRAM_WEB_URL)
        tab_title = _clean_tab_title(str(target_meta.get("title") or "Telegram"))
        return BrowserTarget(
            client_id=f"cdp:{port}",
            tab_id=port,
            tab_title=tab_title,
            tab_url=tab_url,
        )

    def _ensure_tdata_target(
        self,
        profile_dir: Path,
        *,
        launch_browser: bool,
        account: AccountOption | None = None,
    ) -> BrowserTarget | None:
        if _selected_helper_python() is None:
            return None
        if account is not None:
            portable_source = self.inspect_portable_source(account)
            if portable_source.path is not None:
                runtime_state = self.prepare_portable_runtime(account, force=False)
                if not runtime_state.ready_for_export or runtime_state.runtime_dir is None:
                    raise PrimarySurfaceBlocked(
                        runtime_state.detail or "Portable tdata недоступен. Откройте portable Telegram."
                    )
                return BrowserTarget(
                    client_id=f"tdata:{_tdata_target_key(runtime_state.runtime_dir)}",
                    tab_id=0,
                    tab_title="Telegram Desktop",
                    tab_url=str(runtime_state.runtime_dir),
                )
        for tdata_dir in list_candidate_tdata_dirs(profile_dir, include_collector_debug=ALLOW_COLLECTOR_TDATA_DEBUG_FALLBACK):
            try:
                self._run_tdata_helper("list-chats", tdata_dir=tdata_dir, extra_args=["--limit", "5"])
            except Exception as exc:
                self._log_action(f"tdata_unavailable dir={tdata_dir} reason={exc}")
                continue
            return BrowserTarget(
                client_id=f"tdata:{_tdata_target_key(tdata_dir)}",
                tab_id=0,
                tab_title="Telegram Desktop",
                tab_url=str(tdata_dir),
            )
        return None

    def _run_export_via_tdata(
        self,
        *,
        tdata_dir: Path,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        history_limit, timeout_sec = self.preset_limits(preset_key)
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        payload = self._run_tdata_helper(
            "export-chat",
            tdata_dir=tdata_dir,
            extra_args=[
                "--chat-ref",
                chat.fragment,
                "--source",
                "history",
                "--participants-limit",
                "0",
                "--history-limit",
                history_limit,
                "--progress-every",
                TDATA_PROGRESS_EVERY,
            ],
            emit=emit,
            timeout_sec=timeout_sec,
            controller=controller,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else []
        members = rows if isinstance(rows, list) else []
        export_mod._write_markdown(output_path, members, chat.url or chat.fragment, "tdata-history-authors")
        username_rows = export_mod._collect_username_rows(members)
        sidecars = export_mod._write_username_sidecars(output_path, username_rows, chat.url or chat.fragment, "tdata-history-authors")
        self._write_run_log_json(run_log_path, payload)
        stats = payload.get("stats") or {}
        history_messages_scanned = int(stats.get("history_messages_scanned") or 0)
        interrupted = bool(payload.get("interrupted")) or bool(stats.get("interrupted"))
        emit(f"tdata source=history-only")
        emit(f"tdata history_messages={history_messages_scanned}")
        emit(f"tdata usernames={len(username_rows)}")
        if interrupted:
            emit("tdata interrupted=1")
        payload_map = self._run_snapshot_helper(
            output_path=output_path,
            safe_slug=slugify_filename(chat.title or chat.fragment),
            emit=emit,
            run_log_path=run_log_path,
        )
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        usernames_txt = Path(str(sidecars.get("usernames_txt") or output_path.with_name(f"{output_path.stem}_usernames.txt")))
        usernames_json = output_path.with_name(f"{output_path.stem}_usernames.json")
        self._log_action(f"run_success tdata output={output_path} safe_count={safe_count}")
        return ExportResult(
            output_path=output_path,
            usernames_txt=usernames_txt,
            safe_count=safe_count,
            history_messages_scanned=history_messages_scanned,
            usernames_found=len(username_rows),
            interrupted=interrupted,
            safe_txt=safe_txt,
            safe_md=safe_md,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            operation_kind="usernames",
            phones_found=0,
            usernames_json=usernames_json if usernames_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="partial" if interrupted else "done",
        )

    def _run_public_phone_export_via_tdata(
        self,
        *,
        tdata_dir: Path,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        history_limit, timeout_sec = self.preset_limits(preset_key)
        output_path = operation_output_path(output_path, "public_phones")
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        payload = self._run_tdata_helper(
            "export-public-phones",
            tdata_dir=tdata_dir,
            extra_args=[
                "--chat-ref",
                chat.fragment,
                "--history-limit",
                history_limit,
                "--progress-every",
                TDATA_PROGRESS_EVERY,
            ],
            emit=emit,
            timeout_sec=timeout_sec,
            controller=controller,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else []
        phone_rows = rows if isinstance(rows, list) else []
        export_mod._write_public_phones_markdown(output_path, phone_rows, chat.url or chat.fragment, "tdata-public-phones")
        sidecars = export_mod._write_phone_sidecars(output_path, phone_rows, chat.url or chat.fragment, "tdata-public-phones")
        self._write_run_log_json(run_log_path, payload)
        stats = payload.get("stats") or {}
        history_messages_scanned = int(stats.get("history_messages_scanned") or 0)
        interrupted = bool(payload.get("interrupted")) or bool(stats.get("interrupted"))
        private_phone_rows = [r for r in phone_rows if r.get("source_kind") == "user_phone"]
        total_phones_count = len(phone_rows)
        public_phones_count = int(stats.get("public_phones_kept") or 0)
        private_phones_count = int(stats.get("private_phones_kept") or 0)
        if public_phones_count + private_phones_count != total_phones_count:
            private_phones_count = len(private_phone_rows)
            public_phones_count = max(total_phones_count - private_phones_count, 0)
        emit("tdata source=public-phones")
        emit(f"tdata history_messages={history_messages_scanned}")
        emit(f"tdata phones={total_phones_count}")
        emit(f"tdata public_phones={public_phones_count}")
        emit(f"tdata private_phones={private_phones_count}")
        if interrupted:
            emit("tdata interrupted=1")
        phones_txt = Path(str(sidecars.get("phones_txt") or output_path.with_suffix(".txt")))
        phones_json = Path(str(sidecars.get("phones_json") or output_path.with_suffix(".json")))
        # Write private phones sidecars
        private_txt = output_path.with_suffix(".private.txt")
        private_json = output_path.with_suffix(".private.json")
        if private_phone_rows:
            private_header = "username\tfull_name\tphone"
            private_txt_lines = [private_header]
            for row in private_phone_rows:
                private_txt_lines.append(
                    "\t".join([
                        str(row.get("username") or "—").strip() or "—",
                        str(row.get("full_name") or "—").strip() or "—",
                        str(row.get("phone") or "—").strip() or "—",
                    ])
                )
            private_txt.write_text("\n".join(private_txt_lines) + "\n", encoding="utf-8")
            private_json.write_text(
                json.dumps(
                    {
                        "group_url": chat.url or chat.fragment,
                        "source_mode": "tdata-public-phones-private-only",
                        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "count": len(private_phone_rows),
                        "phones": [str(r.get("phone") or "—").strip() for r in private_phone_rows],
                        "rows": private_phone_rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            for stale_path in (private_txt, private_json):
                if stale_path.exists():
                    stale_path.unlink()
        self._log_action(
            f"run_success tdata_public_phones output={output_path} phones={total_phones_count} "
            f"public={public_phones_count} private={private_phones_count}"
        )
        return ExportResult(
            output_path=output_path,
            usernames_txt=None,
            safe_count=0,
            history_messages_scanned=history_messages_scanned,
            usernames_found=0,
            interrupted=interrupted,
            safe_txt=None,
            safe_md=None,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            operation_kind="public_phones",
            phones_found=total_phones_count,
            phones_txt=phones_txt if phones_txt.exists() else None,
            phones_json=phones_json if phones_json.exists() else None,
            private_phones_found=private_phones_count,
            private_phones_txt=private_txt if private_txt.exists() else None,
            private_phones_json=private_json if private_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="partial" if interrupted else "done",
        )

    def _run_tdata_helper(
        self,
        command: str,
        *,
        tdata_dir: Path,
        extra_args: list[str] | None = None,
        emit: Callable[[str], None] | None = None,
        timeout_sec: int | None = None,
        controller: TaskController | None = None,
    ) -> dict[str, Any]:
        helper_python = _selected_helper_python()
        if helper_python is None:
            raise RuntimeError(
                "runtime_unavailable: Telegram helper python не найден. "
                "Запустите scripts/bootstrap_telegram_workstation.sh или укажите TELEGRAM_API_COLLECTOR_PYTHON."
            )
        session_path = TDATA_SESSION_DIR / f"{_tdata_target_key(tdata_dir)}.session"
        TDATA_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        args = [
            str(helper_python[1]),
            str(TDATA_HELPER_SCRIPT),
            command,
            "--tdata",
            str(tdata_dir),
            "--session",
            str(session_path),
        ]
        if extra_args:
            args.extend(extra_args)
        effective_timeout = timeout_sec if timeout_sec is not None else _tdata_helper_timeout_seconds(command)
        with self._tdata_helper_lock:
            run = self.process_runner.run(
                args,
                cwd=str(REPO_ROOT),
                controller=controller,
                timeout_sec=effective_timeout,
                emit_stderr=emit,
                on_cancel_begin=(lambda: emit("Остановка сканирования: завершаем текущий проход...") if emit else None),
            )
            payload: dict[str, Any] | None = None
            if run.forced_cancel:
                raise TaskCancelled("Сканирование остановлено пользователем.")
            if run.timed_out:
                progress_hint = _latest_progress_summary(list(run.stderr_lines))
                suffix = f" Последний прогресс: {progress_hint}." if progress_hint else ""
                if command == "export-chat":
                    raise RuntimeError(
                        f"Скан истории Telegram превысил настроенный лимит {effective_timeout}s.{suffix} "
                        "Уберите TELEGRAM_TDATA_EXPORT_TIMEOUT_SEC или поставьте 0 для полного прохода без лимита. "
                        "Если нужен только короткий тестовый прогон, уменьшите TELEGRAM_TDATA_HISTORY_LIMIT."
                    )
                raise RuntimeError(f"tdata helper timed out after {effective_timeout}s: {command}{suffix}")
            if run.stdout.strip():
                try:
                    parsed = json.loads(run.stdout)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    payload = parsed
            if controller is not None and controller.cancel_requested and run.return_code != 0:
                if payload is not None:
                    return payload
                raise TaskCancelled("Сканирование остановлено пользователем.")
            if run.return_code != 0:
                message = (run.stderr or run.stdout).strip()
                raise RuntimeError(message or f"tdata helper failed: {command}")
            if payload is None:
                try:
                    payload = json.loads(run.stdout)
                except json.JSONDecodeError as exc:
                    if controller is not None and controller.cancel_requested:
                        raise TaskCancelled("Сканирование остановлено пользователем.") from exc
                    raise RuntimeError(f"tdata helper returned invalid JSON for {command}.") from exc
            if not isinstance(payload, dict):
                if controller is not None and controller.cancel_requested:
                    raise TaskCancelled("Сканирование остановлено пользователем.")
                raise RuntimeError(f"tdata helper returned unexpected payload for {command}.")
            return payload

    def _launch_portable_telegram_best_effort(self, profile_dir: Path, tdata_dir: Path) -> None:
        binary_path = find_portable_telegram_binary(profile_dir)
        if binary_path is None:
            return
        workdir = tdata_dir.parent
        try:
            mode = binary_path.stat().st_mode
            if mode & 0o111 == 0:
                binary_path.chmod(mode | 0o755)
        except OSError:
            return
        try:
            subprocess.Popen(
                [str(binary_path), "-workdir", str(workdir)],
                cwd=str(binary_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._log_action(f"portable_launch binary={binary_path} workdir={workdir}")
        except OSError:
            return

    def _run_export_via_cdp(
        self,
        *,
        port: int,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        helper_args = [
            "--url",
            chat.url,
            "--steps",
            CHAT_STEPS,
            "--pause-ms",
            str(max(int(float(export_mod.CHAT_SCROLL_SETTLE_SEC) * 1000), 250)),
            "--timeout-ms",
            str(max(int(CHAT_MAX_RUNTIME) * 1000, 90000)),
        ]
        payload = self._run_cdp_helper(
            "collect-chat",
            port=port,
            timeout_sec=max(int(CHAT_MAX_RUNTIME) + 60, 180),
            extra_args=helper_args,
            controller=controller,
        )
        members = merge_cdp_export_payload(payload)
        export_mod._write_markdown(output_path, members, chat.url, "cdp-simple")
        username_rows = export_mod._collect_username_rows(members)
        sidecars = export_mod._write_username_sidecars(output_path, username_rows, chat.url, "cdp-simple")
        self._write_run_log_json(run_log_path, payload)
        emit(f"simple-cdp members={len(members)}")
        emit(f"simple-cdp usernames={len(username_rows)}")
        payload_map = self._run_snapshot_helper(
            output_path=output_path,
            safe_slug=slugify_filename(chat.url),
            emit=emit,
            run_log_path=run_log_path,
        )
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        usernames_txt = Path(str(sidecars.get("usernames_txt") or output_path.with_name(f"{output_path.stem}_usernames.txt")))
        usernames_json = output_path.with_name(f"{output_path.stem}_usernames.json")
        self._log_action(f"run_success cdp output={output_path} safe_count={safe_count}")
        return ExportResult(
            output_path=output_path,
            usernames_txt=usernames_txt,
            safe_count=safe_count,
            history_messages_scanned=0,
            usernames_found=len(username_rows),
            interrupted=False,
            safe_txt=safe_txt,
            safe_md=safe_md,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            operation_kind="usernames",
            phones_found=0,
            usernames_json=usernames_json if usernames_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="done",
        )

    def _run_export_via_bridge(
        self,
        *,
        account: AccountOption,
        target: BrowserTarget,
        chat: ChatOption,
        output_path: Path,
        emit: Callable[[str], None],
        controller: TaskController | None = None,
        preset_key: str,
        preset_label: str,
        surface_key: str,
        surface_label: str,
        surface_badge: str,
    ) -> ExportResult:
        profile_dir = resolve_profile_dir(account.profile_source)
        run_log_path = ACTION_LOG_DIR / f"export_run_{_utc_timestamp()}.log"
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["SITECTL_TOKEN"] = account.token
        env["SITECTL_BROWSER_PROFILE"] = str(profile_dir)
        env["CHAT_CLIENT_ID"] = target.client_id
        env["SITECTL_SKIP_HUB_BOOT"] = "1"
        chat_steps = CHAT_STEPS
        chat_max_runtime = CHAT_MAX_RUNTIME
        if preset_key == "quick_check":
            chat_steps = str(min(int(CHAT_STEPS), 10))
            chat_max_runtime = str(min(int(CHAT_MAX_RUNTIME), 120))
        command = [
            str(RUN_ONCE_SCRIPT),
            "",
            str(output_path),
            chat.url,
            chat_steps,
            CHAT_DEEP_LIMIT,
            CHAT_TIMEOUT_SEC,
            chat_max_runtime,
            CHAT_DEEP_MODE,
            DEFAULT_MIN_RECORDS,
            target.client_id,
        ]
        run = self.process_runner.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            controller=controller,
            timeout_sec=max(int(chat_max_runtime) + 90, 300),
            emit_stdout=emit,
            emit_stderr=emit,
            on_cancel_begin=(lambda: emit("Остановка bridge-экспорта: завершаем текущий проход...") if emit else None),
        )
        run_log_text = _mask_known_secrets(run.stdout + run.stderr, [account.token, DEFAULT_TOKEN])
        run_log_path.write_text(run_log_text, encoding="utf-8")
        if run.forced_cancel or (controller is not None and controller.cancel_requested and run.return_code != 0):
            raise TaskCancelled("Экспорт остановлен пользователем.")
        if run.timed_out:
            raise RuntimeError(f"Экспорт завершился по timeout. Смотрите лог: {run_log_path}")
        if run.return_code != 0:
            self._log_action(f"run_failed rc={run.return_code} log={run_log_path}")
            raise RuntimeError(f"Экспорт завершился ошибкой. Смотрите лог: {run_log_path}")

        payload_map = self._run_snapshot_helper(
            output_path=output_path,
            safe_slug=slugify_filename(chat.url),
            emit=emit,
            run_log_path=run_log_path,
        )
        usernames_txt = output_path.with_name(f"{output_path.stem}_usernames.txt")
        usernames_json = output_path.with_name(f"{output_path.stem}_usernames.json")
        safe_txt = _optional_path(payload_map.get("safe_txt"))
        safe_md = _optional_path(payload_map.get("safe_md"))
        safe_count = int(payload_map.get("safe_count") or 0)
        self._log_action(f"run_success bridge output={output_path} safe_count={safe_count}")
        return ExportResult(
            output_path=output_path,
            usernames_txt=usernames_txt,
            safe_count=safe_count,
            history_messages_scanned=0,
            usernames_found=safe_count,
            interrupted=False,
            safe_txt=safe_txt,
            safe_md=safe_md,
            log_path=run_log_path,
            action_log_path=self.action_log_path,
            operation_kind="usernames",
            phones_found=0,
            usernames_json=usernames_json if usernames_json.exists() else None,
            surface_key=surface_key,
            surface_label=surface_label,
            surface_badge=surface_badge,
            preset_key=preset_key,
            preset_label=preset_label,
            status="done",
            security_mode=self.preflight_service.security_mode(account.token)[0],
        )

    def _run_cdp_helper(
        self,
        command: str,
        *,
        port: int,
        timeout_sec: int,
        extra_args: list[str] | None = None,
        controller: TaskController | None = None,
    ) -> dict[str, Any]:
        args = ["node", str(CDP_HELPER_SCRIPT), command, "--port", str(port)]
        if extra_args:
            args.extend(extra_args)
        run = self.process_runner.run(
            args,
            cwd=str(REPO_ROOT),
            controller=controller,
            timeout_sec=max(timeout_sec, 5),
        )
        if run.forced_cancel or (controller is not None and controller.cancel_requested and run.return_code != 0):
            raise TaskCancelled("Экспорт остановлен пользователем.")
        if run.timed_out:
            raise RuntimeError(f"CDP helper timed out after {max(timeout_sec, 5)}s: {command}")
        if run.return_code != 0:
            message = (run.stderr or run.stdout or "").strip()
            raise RuntimeError(message or f"CDP helper failed: {command}")
        try:
            payload = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CDP helper returned invalid JSON for {command}.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"CDP helper returned unexpected payload for {command}.")
        return payload

    def _write_run_log_json(self, run_log_path: Path, payload: dict[str, Any]) -> None:
        with run_log_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")

    def _run_snapshot_helper(
        self,
        *,
        output_path: Path,
        safe_slug: str,
        emit: Callable[[str], None],
        run_log_path: Path,
    ) -> dict[str, str]:
        safe_dir = output_path.parent / f"telegram_export_{safe_slug}"
        snapshot_cmd = [
            sys.executable,
            str(SAFE_SNAPSHOT_SCRIPT),
            "--source-md",
            str(output_path),
            "--directory",
            str(safe_dir),
        ]
        snapshot = subprocess.run(
            snapshot_cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if snapshot.stdout:
            for line in snapshot.stdout.splitlines():
                emit(line)
        if snapshot.stderr:
            for line in snapshot.stderr.splitlines():
                emit(line)
        if snapshot.returncode != 0:
            self._log_action(f"safe_snapshot_failed rc={snapshot.returncode} output={output_path}")
            raise RuntimeError(f"Экспорт сохранён, но safe snapshot не построен. Смотрите лог: {run_log_path}")
        return parse_key_value_output(snapshot.stdout)

    def _find_active_cdp_port(self, profile_dir: Path) -> int | None:
        state = self._load_cdp_state(profile_dir)
        if state is None:
            return None
        port_value = state.get("port")
        try:
            port = int(port_value)
        except (TypeError, ValueError):
            return None
        return port if _cdp_debugger_ready(port) else None

    def _load_cdp_state(self, profile_dir: Path) -> dict[str, Any] | None:
        state_path = _cdp_state_path(profile_dir)
        if not state_path.exists():
            return None
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _save_cdp_state(self, profile_dir: Path, *, port: int) -> None:
        state_path = _cdp_state_path(profile_dir)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"profile_dir": str(profile_dir), "port": int(port)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _launch_cdp_browser(self, profile_dir: Path) -> int:
        browser = _detect_browser_binary()
        port = _pick_free_cdp_port(profile_dir)
        log_path = ACTION_LOG_DIR / f"browser_cdp_{_utc_timestamp()}.log"
        profile_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [
                    browser,
                    f"--user-data-dir={profile_dir}",
                    f"--remote-debugging-port={port}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--new-window",
                    TELEGRAM_WEB_URL,
                ],
                cwd=str(REPO_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._save_runtime_owner("cdp_browser", pid=process.pid, extra={"port": int(port), "profile_dir": str(profile_dir)})
        deadline = time.time() + 30
        while time.time() < deadline:
            if _cdp_debugger_ready(port):
                self._save_cdp_state(profile_dir, port=port)
                self._log_action(f"cdp_ready port={port} profile={profile_dir}")
                return port
            time.sleep(0.5)
        raise RuntimeError(
            f"Не удалось запустить Telegram в браузерном профиле. Закройте этот профиль в других окнах Chrome и повторите. Лог: {log_path}"
        )

    def _is_cdp_target(self, target: BrowserTarget | None) -> bool:
        return bool(target and str(target.client_id or "").startswith("cdp:"))

    def _cdp_port_from_target(self, target: BrowserTarget | None) -> int | None:
        if target is None:
            return None
        match = re.fullmatch(r"cdp:(\d+)", str(target.client_id or "").strip())
        if match:
            return int(match.group(1))
        if target.tab_id > 0 and _cdp_debugger_ready(target.tab_id):
            return int(target.tab_id)
        return None

    def _is_tdata_target(self, target: BrowserTarget | None) -> bool:
        return bool(target and str(target.client_id or "").startswith("tdata:"))

    def _tdata_dir_from_target(self, target: BrowserTarget | None) -> Path | None:
        if target is None:
            return None
        if self._is_tdata_target(target):
            path = Path(str(target.tab_url or "")).expanduser()
            return path if path.exists() else None
        return None

    def _ensure_hub(self, token: str) -> None:
        try:
            export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=1.5)
            return
        except RuntimeError as exc:
            if "HTTP 401" in str(exc):
                raise RuntimeError(
                    "Hub уже запущен с другим токеном. Остановите старый hub или используйте тот же SITECTL token."
                ) from exc

        hub_pids = self._hub_listener_pids()
        if hub_pids:
            owned = self._owned_runtime_pid("hub")
            if owned is not None and owned in hub_pids:
                self._terminate_owned_runtime("hub")
            else:
                raise RuntimeError(
                    "Порт 8765 уже занят чужим процессом. GUI не будет убивать его автоматически; "
                    "освободите порт или используйте уже запущенный hub."
                )
        log_path = ACTION_LOG_DIR / "hub_gui_boot.log"
        ACTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "webcontrol",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                    "--token",
                    token,
                    "--state-file",
                    str(load_runtime_settings(mutate=True).hub_state_file),
                ],
                cwd=str(REPO_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._save_runtime_owner(
            "hub",
            pid=process.pid,
            extra={"state_file": str(load_runtime_settings(mutate=True).hub_state_file)},
        )
        deadline = time.time() + 6
        while time.time() < deadline:
            try:
                export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=1.0)
                self._log_action("hub_ready")
                return
            except RuntimeError:
                time.sleep(0.25)
        raise RuntimeError(f"Не удалось поднять hub. Лог: {log_path}")

    def _hub_listener_pids(self) -> list[int]:
        cmd = "ss -ltnp 'sport = :8765' 2>/dev/null | sed -n 's/.*pid=\\([0-9]\\+\\).*/\\1/p' | sort -u"
        result = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, check=False)
        pids: list[int] = []
        for raw in result.stdout.splitlines():
            value = raw.strip()
            if not value.isdigit():
                continue
            pids.append(int(value))
        return pids

    def _runtime_owner_path(self, name: str) -> Path:
        return RUNTIME_OWNERS_DIR / f"{name}.json"

    def _save_runtime_owner(self, name: str, *, pid: int, extra: dict[str, Any] | None = None) -> None:
        RUNTIME_OWNERS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"pid": int(pid), "updated_at": _utc_timestamp()}
        if extra:
            payload.update(extra)
        self._runtime_owner_path(name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load_runtime_owner(self, name: str) -> dict[str, Any] | None:
        path = self._runtime_owner_path(name)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _owned_runtime_pid(self, name: str) -> int | None:
        payload = self._load_runtime_owner(name)
        if not isinstance(payload, dict):
            return None
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            return None
        return pid if pid > 0 else None

    def _terminate_owned_runtime(self, name: str) -> None:
        pid = self._owned_runtime_pid(name)
        if pid is None:
            return
        try:
            os.kill(pid, signal.SIGTERM)
            self._log_action(f"{name}_owned_runtime_stopped pid={pid}")
        except OSError:
            return
        deadline = time.time() + 2
        while time.time() < deadline and _pid_is_alive(pid):
            time.sleep(0.1)
        if _pid_is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def _hub_reachable(self, token: str) -> bool:
        try:
            export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=0.8)
        except RuntimeError:
            return False
        return True

    def _inspect_hub_token_state(self, token: str) -> dict[str, Any]:
        hub_pids = self._hub_listener_pids()
        if not hub_pids:
            return {"state": "offline", "detail": "", "restart_available": False}
        try:
            export_mod._http_json(HUB_URL, token, "GET", "/api/clients", request_timeout_sec=0.8)
        except RuntimeError as exc:
            text = str(exc or "").strip()
            if "HTTP 401" in text:
                owned = self._owned_runtime_pid("hub")
                if owned is not None and owned in hub_pids:
                    return {
                        "state": "owned_mismatch",
                        "detail": "Hub на :8765 уже запущен этим GUI с другим токеном.",
                        "restart_available": True,
                    }
                return {
                    "state": "foreign_mismatch",
                    "detail": "На :8765 уже живёт внешний hub/process с другим токеном. GUI не будет убивать его автоматически.",
                    "restart_available": False,
                }
            return {
                "state": "error",
                "detail": _compact_error_text(text) or "Hub на :8765 сейчас недоступен.",
                "restart_available": False,
            }
        return {"state": "ok", "detail": "", "restart_available": False}

    def _foreign_hub_warning(self) -> str:
        hub_pids = self._hub_listener_pids()
        if not hub_pids:
            return ""
        owned = self._owned_runtime_pid("hub")
        if owned is None or owned not in hub_pids:
            return "Порт 8765 занят внешним hub/process; GUI не будет убивать его автоматически."
        return ""

    def _count_stale_runtime_files(self) -> int:
        stale = 0
        cdp_dir = RUNTIME_DIR / "cdp"
        state_paths = list(cdp_dir.glob("*.json")) if cdp_dir.exists() else []
        for state_path in state_paths:
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stale += 1
                continue
            try:
                port = int(payload.get("port") or 0)
            except (TypeError, ValueError):
                stale += 1
                continue
            if port <= 0 or not _cdp_debugger_ready(port):
                stale += 1
        return stale

    def _prune_runtime_artifacts(self) -> None:
        for directory in (ACTION_LOG_DIR, RUNTIME_DIR / "cdp", RUNTIME_OWNERS_DIR):
            if not directory.exists():
                continue
            files = sorted((item for item in directory.iterdir() if item.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
            for extra in files[40:]:
                try:
                    extra.unlink()
                except OSError:
                    continue

    def _list_clients(self, token: str) -> list[dict[str, Any]]:
        payload = export_mod._http_json_retry(HUB_URL, token, "GET", "/api/clients", retries=2, request_timeout_sec=2.0)
        clients = payload.get("clients") or []
        return clients if isinstance(clients, list) else []

    def _resolve_best_client(
        self,
        token: str,
        *,
        known_client_ids: set[str | None],
        require_online: bool,
    ) -> BrowserTarget | None:
        clients = self._list_clients(token)
        rows: list[tuple[int, int, int, str, str, int, str, str]] = []
        for client in clients:
            client_id = str(client.get("client_id") or "").strip()
            if not client_id:
                continue
            is_online = 1 if bool(client.get("is_online")) else 0
            if require_online and not is_online:
                continue
            tabs = client.get("tabs") or []
            if not isinstance(tabs, list):
                tabs = []
            telegram_tabs = [tab for tab in tabs if "web.telegram.org" in str(tab.get("url") or "")]
            if not telegram_tabs:
                continue
            selected_tab = _pick_telegram_tab(telegram_tabs)
            if not selected_tab:
                continue
            tab_id = selected_tab.get("id")
            if not isinstance(tab_id, int):
                continue
            is_new = 1 if client_id not in known_client_ids else 0
            dialog_tab = 1 if "/#" in str(selected_tab.get("url") or "") else 0
            last_seen = str(client.get("last_seen") or "")
            rows.append(
                (
                    is_new,
                    is_online,
                    dialog_tab,
                    last_seen,
                    client_id,
                    tab_id,
                    _clean_tab_title(str(selected_tab.get("title") or "")),
                    str(selected_tab.get("url") or ""),
                )
            )
        if not rows:
            return None
        rows.sort(reverse=True)
        _is_new, _is_online, _dialog_tab, _last_seen, client_id, tab_id, title, url = rows[0]
        return BrowserTarget(client_id=client_id, tab_id=tab_id, tab_title=title, tab_url=url)

    def _refresh_target(self, token: str, client_id: str, tab_id: int) -> BrowserTarget:
        clients = self._list_clients(token)
        selected_online = False
        for client in clients:
            if str(client.get("client_id") or "").strip() != client_id:
                continue
            selected_online = bool(client.get("is_online"))
            break
        if not selected_online:
            replacement = self._resolve_best_client(token, known_client_ids=set(), require_online=True)
            if replacement is None:
                raise RuntimeError("Нет живого Telegram-клиента. Нажмите 'Подключить Telegram'.")
            return replacement
        try:
            resolved_client_id, resolved_tab_id = export_mod._find_tab(clients, client_id=client_id, tab_id=tab_id, url_pattern="")
        except RuntimeError:
            resolved_client_id, resolved_tab_id = export_mod._find_tab(clients, client_id=client_id, tab_id=None, url_pattern="")
        tab_url, tab_title = export_mod._get_tab_meta_best_effort(HUB_URL, token, resolved_client_id, resolved_tab_id, timeout_sec=1.2)
        return BrowserTarget(
            client_id=resolved_client_id,
            tab_id=resolved_tab_id,
            tab_title=_clean_tab_title(tab_title),
            tab_url=str(tab_url or ""),
        )

    def _log_action(self, message: str) -> None:
        self.action_log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.action_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp}\t{message}\n")

    def _wait_for_chat_list_ready(self, token: str, client_id: str, tab_id: int) -> None:
        export_mod._send_command_result(
            server=HUB_URL,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=4,
            command={
                "type": "wait_selector",
                "selector": CHAT_LIST_READY_SELECTOR,
                "timeout_ms": 3000,
                "visible_only": False,
            },
            raise_on_fail=False,
        )



__all__ = ["TelegramGuiBackend"]

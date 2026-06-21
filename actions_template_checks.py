from __future__ import annotations

import threading

from app_config import *


class ActionsTemplateChecksMixin:
    def _check_templates(self) -> None:
        """Check bundled templates without freezing the startup UI.

        Embedded DOCX templates may need base64 decoding/extraction in one-file EXE
        mode. That is moved off the Tk thread so the window appears responsive.
        """
        def worker() -> None:
            try:
                from medical_constants import DOCUMENT_ORDER
                from medical_paths import bundled_template_path

                missing = []
                for kind in DOCUMENT_ORDER:
                    template_path = bundled_template_path(kind)
                    if not template_path.exists():
                        missing.append(template_path)
                ok = not missing
                payload = missing
            except Exception as exc:
                ok = False
                payload = [exc]

            def apply_result() -> None:
                if ok:
                    self._log("\n✅ Встроенные медицинские шаблоны найдены.\n")
                    return
                self._log("\n❌ Не найдены встроенные шаблоны:\n")
                for item in payload:
                    self._log(f"- {item}\n")
                self._log("Проверьте папку templates рядом с программой или сборку EXE с --add-data.\n")

            try:
                self.root.after(0, apply_result)
            except Exception:
                pass

        threading.Thread(target=worker, name="template-check", daemon=True).start()

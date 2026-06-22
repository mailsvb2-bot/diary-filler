from __future__ import annotations

from dialog_dates import DialogDatesMixin
from dialog_document_details import DialogDocumentDetailsMixin
from dialog_expert import DialogExpertMixin
from dialog_fields import DialogFieldsMixin


class DialogsMixin(DialogDatesMixin, DialogDocumentDetailsMixin, DialogExpertMixin, DialogFieldsMixin):
    pass

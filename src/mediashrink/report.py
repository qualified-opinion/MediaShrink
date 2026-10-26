"""Per-batch CSV log in the output folder recording which output came from which original."""
import csv
from datetime import datetime
from pathlib import Path

COLUMNS = ('Original file', 'Output file', 'Original bytes', 'Output bytes', 'Saved bytes', 'Saved %', 'Result', 'Details')


class ResultsLog:
    def __init__(self, destination):
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        for number in range(1000):
            suffix = '' if number == 0 else f'-{number}'
            self.path = Path(destination) / f'mediashrink-results-{stamp}{suffix}.csv'
            try:
                # utf-8-sig lets spreadsheet apps read non-English file names correctly.
                self.file = open(self.path, 'x', newline='', encoding='utf-8-sig')
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError('Too many results logs with the same name')
        self.writer = csv.writer(self.file)
        self.error = None
        self.write(COLUMNS)

    def add(self, source, result, details='', original=None, target=None, size=None):
        saved = original - size if target else None
        self.write((
            source, target or '', '' if original is None else original, size if target else '',
            '' if saved is None else saved, f'{100 * saved / original:.1f}' if target and original else '',
            result, details,
        ))

    def write(self, row):
        if self.error is not None:
            return
        try:
            self.writer.writerow(row)
            self.file.flush()  # Completed rows survive an application crash.
        except OSError as exc:
            self.error = exc

    def close(self):
        try:
            self.file.close()
        except OSError as exc:
            self.error = self.error or exc

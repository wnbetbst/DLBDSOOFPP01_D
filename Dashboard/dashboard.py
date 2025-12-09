from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


class ModuleStatus(str, Enum):
    """Interner Status eines Moduls."""

    PLANNED = "planned"
    ENROLLED = "enrolled"
    COMPLETED = "completed"
    RECOGNIZED = "recognized"

    def label(self) -> str:
        """Deutschsprachige Bezeichnung für die Anzeige."""
        mapping = {
            ModuleStatus.PLANNED: "Geplant",
            ModuleStatus.ENROLLED: "Eingeschrieben",
            ModuleStatus.COMPLETED: "Abgeschlossen",
            ModuleStatus.RECOGNIZED: "Anerkannt",
        }
        return mapping[self]


@dataclass
class Assessment:
    name: str
    max_points: float
    passed: bool = False
    grade: Optional[float] = None

    def record_result(self, passed: bool, grade: Optional[float]) -> None:
        """
        Ergebnis der Prüfungsleistung festhalten.

        - passed: gibt an, ob die Leistung bestanden ist (z.B. Note <= 4,0 oder Anerkennung).
        - grade: Note, falls vorhanden. Bei anerkannten Leistungen bleibt grade = None.
        """
        # Eingabe wird bewusst nicht weiter geprüft, da Anerkennungen keine Note benötigen
        self.passed = passed
        # Wenn bestanden, aber keine Note (z.B. Anerkennung), bleibt grade = None
        self.grade = grade if passed and grade is not None else (None if passed else None)

    def is_passed(self) -> bool:
        """
        Liefert True, wenn die Prüfungsleistung als bestanden gilt.

        Die Information wird primär über das Feld `passed` abgebildet.
        Optional könnte hier eine zusätzliche Logik auf Basis der Note ergänzt werden.
        """
        return self.passed


@dataclass
class Module:
    id: Optional[int]  # fachliche ID des Moduls für CLI-Auswahl und Modell
    code: str
    title: str
    ects: int
    assessment: Assessment
    status: ModuleStatus = ModuleStatus.PLANNED

    def enroll(self) -> None:
        # Einschreibung ohne Bewertung
        self.status = ModuleStatus.ENROLLED

    def complete(self, grade: float) -> None:
        # Abschluss setzt Note und markiert Status
        self.assessment.record_result(True, grade)
        self.status = ModuleStatus.COMPLETED

    def recognize(self) -> None:
        """Modul als anerkannt markieren: ECTS zählen, aber keine Note."""
        self.assessment.record_result(True, None)
        self.status = ModuleStatus.RECOGNIZED

    def reset(self) -> None:
        self.assessment.record_result(False, None)
        self.status = ModuleStatus.PLANNED


@dataclass
class Semester:
    semester: int
    modules: List[Module] = field(default_factory=list)

    def add_module(self, module: Module) -> None:
        self.modules.append(module)

    def get_module(self, code: str) -> Optional[Module]:
        return next((m for m in self.modules if m.code == code), None)


class Goal:
    description: str

    def is_met(self, context: "ProgramSnapshot") -> bool:
        raise NotImplementedError

    def progress(self, context: "ProgramSnapshot") -> float:
        raise NotImplementedError


@dataclass
class DurationGoal(Goal):
    planned_semesters: int
    description: str = "Studium in geplanter Zeit abschließen"

    def is_met(self, context: "ProgramSnapshot") -> bool:
        return context.completed_semesters <= self.planned_semesters

    def progress(self, context: "ProgramSnapshot") -> float:
        if context.completed_semesters == 0 or self.planned_semesters == 0:
            return 0.0
        ratio = context.completed_semesters / self.planned_semesters
        return max(0.0, min(1.0, ratio))


@dataclass
class GPAgoal(Goal):
    max_gpa: float
    description: str = "Notenschnitt halten"

    def is_met(self, context: "ProgramSnapshot") -> bool:
        return context.current_gpa is not None and context.current_gpa <= self.max_gpa

    def progress(self, context: "ProgramSnapshot") -> float:
        if context.current_gpa is None or context.current_gpa == 0:
            return 0.0
        ratio = self.max_gpa / context.current_gpa
        return max(0.0, min(1.0, ratio))


@dataclass
class ProgramSnapshot:
    modules: List[Module]
    completed_modules: List[Module]
    enrolled_modules: List[Module]
    planned_modules: List[Module]
    recognized_modules: List[Module]
    ects_completed: int
    ects_enrolled: int
    total_ects: int
    current_gpa: Optional[float]
    completed_semesters: int


@dataclass
class StudyProgram:
    name: str
    total_ects: int
    semesters: List[Semester] = field(default_factory=list)
    goals: List[Goal] = field(default_factory=list)

    def add_semester(self, semester: Semester) -> None:
        self.semesters.append(semester)

    def find_module(self, code: str) -> Optional[Module]:
        for semester in self.semesters:
            module = semester.get_module(code)
            if module:
                return module
        return None

    def all_modules(self) -> List[Module]:
        return [m for semester in self.semesters for m in semester.modules]

    def snapshot(self) -> ProgramSnapshot:
        modules = self.all_modules()
        completed = [m for m in modules if m.status == ModuleStatus.COMPLETED]
        enrolled = [m for m in modules if m.status == ModuleStatus.ENROLLED]
        planned = [m for m in modules if m.status == ModuleStatus.PLANNED]
        recognized = [m for m in modules if m.status == ModuleStatus.RECOGNIZED]

        # Anerkannte Module zählen ebenfalls zu den abgeschlossenen ECTS
        ects_completed = sum(m.ects for m in completed + recognized)
        ects_enrolled = sum(m.ects for m in enrolled)
        # GPA nur aus Modulen mit Note, damit Anerkennungen den Schnitt nicht verfälschen
        gpa = self._calculate_gpa(completed)

        # Semester gilt als abgeschlossen, wenn alle Module abgeschlossen ODER anerkannt sind
        completed_semesters = sum(
            1
            for semester in self.semesters
            if semester.modules
            and all(
                m.status in (ModuleStatus.COMPLETED, ModuleStatus.RECOGNIZED)
                for m in semester.modules
            )
        )

        return ProgramSnapshot(
            modules=modules,
            completed_modules=completed,
            enrolled_modules=enrolled,
            planned_modules=planned,
            recognized_modules=recognized,
            ects_completed=ects_completed,
            ects_enrolled=ects_enrolled,
            total_ects=self.total_ects,
            current_gpa=gpa,
            completed_semesters=completed_semesters,
        )

    @staticmethod
    def _calculate_gpa(completed_modules: Iterable[Module]) -> Optional[float]:
        graded = [m for m in completed_modules if m.assessment.grade is not None]
        if not graded:
            return None
        weighted_sum = sum(m.assessment.grade * m.ects for m in graded)
        ects_sum = sum(m.ects for m in graded)
        return round(weighted_sum / ects_sum, 2) if ects_sum else None


class DashboardViewModel:
    def __init__(self, program: StudyProgram) -> None:
        self.program = program

    def progress_bar(self, width: int = 30) -> str:
        snapshot = self.program.snapshot()
        if snapshot.total_ects == 0:
            return "[Keine Ziel-ECTS konfiguriert]"
        ratio = snapshot.ects_completed / snapshot.total_ects
        # Breite der Balkenanzeige bleibt konstant, nur der gefüllte Anteil variiert
        filled = int(ratio * width)
        return f"[{'#' * filled}{'-' * (width - filled)}] {ratio:.0%} ({snapshot.ects_completed}/{snapshot.total_ects} ECTS)"

    def goal_descriptions(self) -> List[str]:
        snapshot = self.program.snapshot()
        descriptions = []
        for goal in self.program.goals:
            met = "erfüllt" if goal.is_met(snapshot) else "offen"
            # Pro Ziel eine formatierte Zeile erzeugen, damit CLI die Liste einfach ausgeben kann
            descriptions.append(f"{goal.description}: {goal.progress(snapshot)*100:.0f}% ({met})")
        return descriptions

    def bucket_counts(self) -> Dict[str, int]:
        snapshot = self.program.snapshot()
        return {
            "Abgeschlossen": len(snapshot.completed_modules),
            "Eingeschrieben": len(snapshot.enrolled_modules),
            "Geplant": len(snapshot.planned_modules),
            "Anerkannt": len(snapshot.recognized_modules),
        }

    def grade_summary(self) -> str:
        gpa = self.program.snapshot().current_gpa
        return f"Aktueller Notenschnitt: {gpa:.2f}" if gpa is not None else "Noch keine Noten gespeichert."

    def module_table(self, modules: Iterable[Module], id_map: Optional[Dict[str, int]] = None) -> str:
        """Tabellarische Darstellung mit festen Spaltenbreiten, damit ECTS/Status sauber ausgerichtet bleiben."""
        title_width = 48
        code_width = 14

        def short(text: str, width: int) -> str:
            return text if len(text) <= width else text[: width - 3] + "..."

        if id_map:
            headers = f"{'ID':<4} {'Code':<{code_width}} {'Titel':<{title_width}} {'ECTS':>4}  {'Status':<12} {'Note':<5}"
        else:
            headers = f"{'Code':<{code_width}} {'Titel':<{title_width}} {'ECTS':>4}  {'Status':<12} {'Note':<5}"
        lines = [headers, "-" * len(headers)]

        for module in modules:
            grade = f"{module.assessment.grade:.1f}" if module.assessment.grade is not None else "-"
            code = short(module.code, code_width)
            title = short(module.title, title_width)
            if id_map:
                id_str = str(id_map.get(module.code, ""))
                lines.append(
                    f"{id_str:<4} {code:<{code_width}} {title:<{title_width}} {module.ects:>4}  {module.status.label():<12} {grade:<5}"
                )
            else:
                lines.append(
                    f"{code:<{code_width}} {title:<{title_width}} {module.ects:>4}  {module.status.label():<12} {grade:<5}"
                )
        return "\n".join(lines)


class PersistenceService:
    @staticmethod
    def save(program: StudyProgram, path: Path) -> None:
        # Datenmodell flach in JSON serialisieren, damit CLI und andere Clients es leicht konsumieren können
        payload = {
            "name": program.name,
            "total_ects": program.total_ects,
            "goals": [PersistenceService._serialize_goal(goal) for goal in program.goals],
            "semesters": [
                {
                    "semester": semester.semester,
                    "modules": [
                        {
                            "id": module.id,
                            "code": module.code,
                            "title": module.title,
                            "ects": module.ects,
                            "status": module.status.value,
                            "assessment": asdict(module.assessment),
                        }
                        for module in semester.modules
                    ],
                }
                for semester in program.semesters
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> StudyProgram:
        # Unterstützt sowohl aktuelle Dateien als auch alte Strukturen mit 'number'-Feld
        payload = json.loads(path.read_text(encoding="utf-8"))
        program = StudyProgram(payload["name"], payload["total_ects"])

        for goal_payload in payload.get("goals", []):
            program.goals.append(PersistenceService._deserialize_goal(goal_payload))

        for semester_payload in payload["semesters"]:
            sem_value = semester_payload.get("semester", semester_payload.get("number"))
            if sem_value is None:
                raise KeyError("Semester-Eintrag benötigt das Feld 'semester' (oder legacy 'number').")
            semester = Semester(sem_value)
            for module_payload in semester_payload["modules"]:
                assessment_data = module_payload["assessment"]
                assessment = Assessment(
                    name=assessment_data["name"],
                    max_points=assessment_data["max_points"],
                    passed=assessment_data.get("passed", False),
                    grade=assessment_data.get("grade"),
                )
                module = Module(
                    id=module_payload.get("id"),  # Kann bei alten Dateien None sein
                    code=module_payload["code"],
                    title=module_payload["title"],
                    ects=module_payload["ects"],
                    status=ModuleStatus(module_payload["status"]),
                    assessment=assessment,
                )
                semester.add_module(module)
            program.add_semester(semester)

        # Sicherstellen, dass alle Module eine eindeutige ID besitzen
        PersistenceService._ensure_module_ids(program)
        return program

    @staticmethod
    def _ensure_module_ids(program: StudyProgram) -> None:
        """
        Stellt sicher, dass alle Module eine eindeutige numerische ID besitzen.
        Für ältere Datendateien ohne ID werden IDs nachträglich vergeben.
        """
        modules = program.all_modules()
        used_ids = {m.id for m in modules if m.id is not None}
        next_id = max(used_ids) + 1 if used_ids else 1

        for module in modules:
            if module.id is None:
                module.id = next_id
                next_id += 1

    @staticmethod
    def _serialize_goal(goal: Goal) -> Dict:
        if isinstance(goal, DurationGoal):
            return {
                "type": "duration",
                "description": goal.description,
                "planned_semesters": goal.planned_semesters,
            }
        if isinstance(goal, GPAgoal):
            return {
                "type": "gpa",
                "description": goal.description,
                "max_gpa": goal.max_gpa,
            }
        raise ValueError(f"Unbekannter Zieltyp: {type(goal)}")

    @staticmethod
    def _deserialize_goal(payload: Dict) -> Goal:
        goal_type = payload.get("type")
        if goal_type == "duration":
            return DurationGoal(
                planned_semesters=payload["planned_semesters"],
                description=payload.get("description", "Studium in geplanter Zeit abschließen"),
            )
        if goal_type == "gpa":
            return GPAgoal(
                max_gpa=payload["max_gpa"],
                description=payload.get("description", "Notenschnitt halten"),
            )
        raise ValueError(f"Unbekannter Zieltyp: {goal_type}")


class InputValidator:
    """
    Zentrale Hilfsklasse für die Validierung und Konvertierung von Nutzereingaben.
    Dient dazu, die Eingabelogik aus der CLI zu entkoppeln und wiederverwendbar zu machen.
    """

    @staticmethod
    def parse_int(raw: str, error_message: str = "Ungültige Zahl.") -> int:
        try:
            return int(raw)
        except ValueError as exc:
            # Fehler bleibt als ValueError erhalten, damit die CLI ihn gesammelt abfangen kann
            raise ValueError(error_message) from exc

    @staticmethod
    def parse_float(raw: str, error_message: str = "Ungültige Zahl.") -> float:
        try:
            return float(raw)
        except ValueError as exc:
            # Gleiche Strategie wie parse_int, damit alle Eingaben einheitlich geprüft sind
            raise ValueError(error_message) from exc

    @staticmethod
    def ensure_non_empty(raw: str, error_message: str = "Eingabe darf nicht leer sein.") -> str:
        if not raw.strip():
            raise ValueError(error_message)
        return raw.strip()


class DashboardCLI:
    def __init__(self, program: StudyProgram, data_path: Path) -> None:
        self.program = program
        self.data_path = data_path

    def run(self) -> None:
        while True:
            self._print_overview()
            choice = input(
                "\nAktion auswählen:\n"
                " [1] Module auflisten\n"
                " [2] Modulstatus ändern\n"
                " [3] Modul hinzufügen\n"
                " [4] Notenübersicht\n"
                " [0] Beenden\n"
                "\nEingabe: "
            ).strip()
            try:
                if choice == "1":
                    self._list_modules()
                elif choice == "2":
                    self._update_module()
                elif choice == "3":
                    self._add_module()
                elif choice == "4":
                    self._show_grades()
                elif choice == "0":
                    print("Bis bald!")
                    return
            except ValueError as exc:
                print(f"Warnung: {exc}")

    def _print_overview(self) -> None:
        vm = DashboardViewModel(self.program)
        # Kurze Zusammenfassung des Fortschritts als Einstieg für jede Interaktion
        print("\n" + "=" * 60)
        print(self.program.name)
        print(vm.progress_bar())
        print(vm.grade_summary())

        # Ziele
        print("\nZiele:")
        for goal_line in vm.goal_descriptions():
            print(f"- {goal_line}")

        # Modulstatus
        print("\nModulstatus:")
        for bucket, count in vm.bucket_counts().items():
            print(f"{bucket}: {count}")

    def _build_indexes(self, snapshot: ProgramSnapshot) -> Tuple[Dict[int, Module], Dict[str, int]]:
        """
        Erstellt Mapping von fachlicher Modul-ID -> Modul
        und Modulcode -> fachliche ID.

        Damit arbeitet die CLI nicht mehr mit reinen Listenpositionen, sondern mit stabilen IDs.
        """
        id_index: Dict[int, Module] = {}
        code_index: Dict[str, int] = {}
        for module in snapshot.modules:
            if module.id is None:
                raise ValueError(f"Modul {module.code} besitzt keine ID.")
            id_index[module.id] = module
            code_index[module.code] = module.id
        return id_index, code_index

    def _list_modules(self) -> None:
        vm = DashboardViewModel(self.program)
        snapshot = self.program.snapshot()
        _, code_index = self._build_indexes(snapshot)

        print("\n--- Abgeschlossene Module ---")
        print(vm.module_table(snapshot.completed_modules, id_map=code_index))
        print("\n--- Anerkannte Module ---")
        if snapshot.recognized_modules:
            print(vm.module_table(snapshot.recognized_modules, id_map=code_index))
        else:
            print("Keine anerkannten Module.")
        print("\n--- Eingeschriebene Module ---")
        print(vm.module_table(snapshot.enrolled_modules, id_map=code_index))
        print("\n--- Geplante Module ---")
        print(vm.module_table(snapshot.planned_modules, id_map=code_index))

    def _update_module(self) -> None:
        vm = DashboardViewModel(self.program)
        snapshot = self.program.snapshot()
        id_index, code_index = self._build_indexes(snapshot)

        # Übersicht mit IDs anzeigen
        print("\n--- Abgeschlossene Module ---")
        print(vm.module_table(snapshot.completed_modules, id_map=code_index))
        print("\n--- Anerkannte Module ---")
        if snapshot.recognized_modules:
            print(vm.module_table(snapshot.recognized_modules, id_map=code_index))
        else:
            print("Keine anerkannten Module.")
        print("\n--- Eingeschriebene Module ---")
        print(vm.module_table(snapshot.enrolled_modules, id_map=code_index))
        print("\n--- Geplante Module ---")
        print(vm.module_table(snapshot.planned_modules, id_map=code_index))
        print()

        raw = input("Modulcode ODER ID für die Aktualisierung (0 = Abbrechen): ").strip()
        if raw == "0":
            print("Vorgang abgebrochen.")
            return

        module: Optional[Module] = None

        if raw.isdigit():
            module_id = InputValidator.parse_int(raw, "Ungültige ID.")
            module = id_index.get(module_id)
            if not module:
                raise ValueError(f"Kein Modul mit ID {module_id} gefunden.")
        else:
            code = raw.upper()
            module = self.program.find_module(code)
            if not module:
                raise ValueError(f"Modul {code} nicht gefunden.")

        print(f"Aktueller Status von {module.code}: {module.status.label()}")
        print("Neuer Status:")
        print(" [1] Geplant")
        print(" [2] Eingeschrieben")
        print(" [3] Abgeschlossen")
        print(" [4] Anerkannt")
        print()
        status_choice = input("Auswahl (1-4, 0 = Abbrechen): ").strip()

        if status_choice == "0":
            print("Vorgang abgebrochen.")
            return

        mapping = {
            "1": ModuleStatus.PLANNED,
            "2": ModuleStatus.ENROLLED,
            "3": ModuleStatus.COMPLETED,
            "4": ModuleStatus.RECOGNIZED,
        }
        if status_choice not in mapping:
            raise ValueError("Ungültige Auswahl.")

        target_status = mapping[status_choice]
        if target_status == ModuleStatus.PLANNED:
            module.reset()
        elif target_status == ModuleStatus.ENROLLED:
            module.enroll()
        elif target_status == ModuleStatus.COMPLETED:
            grade_input = input("Note (z.B. 1.7, 0 = Abbrechen): ").strip().replace(",", ".")
            if grade_input == "0":
                print("Vorgang abgebrochen.")
                return
            grade = InputValidator.parse_float(grade_input, "Ungültige Note.")
            module.complete(grade)
        elif target_status == ModuleStatus.RECOGNIZED:
            module.recognize()

        # Nach erfolgreicher Änderung automatisch speichern
        PersistenceService.save(self.program, self.data_path)
        print(f"Status von {module.code} aktualisiert und gespeichert.")

    def _add_module(self) -> None:
        raw_semester = input("Semester (Zahl, z.B. 1, 0 = Abbrechen): ").strip()
        if raw_semester == "0":
            print("Vorgang abgebrochen.")
            return

        semester_number = InputValidator.parse_int(raw_semester, "Ungültige Semestereingabe.")

        semester = next((s for s in self.program.semesters if s.semester == semester_number), None)
        if semester is None:
            raise ValueError(f"Semester {semester_number} existiert nicht.")

        code_raw = input("Modulcode (z.B. MAT101, 0 = Abbrechen): ").strip().upper()
        if code_raw == "0":
            print("Vorgang abgebrochen.")
            return
        code = InputValidator.ensure_non_empty(code_raw, "Modulcode darf nicht leer sein.").upper()
        if self.program.find_module(code):
            raise ValueError(f"Ein Modul mit dem Code {code} existiert bereits.")

        title_raw = input("Modultitel (0 = Abbrechen): ").strip()
        if title_raw == "0":
            print("Vorgang abgebrochen.")
            return
        title = InputValidator.ensure_non_empty(title_raw, "Modultitel darf nicht leer sein.")

        raw_ects = input("ECTS (0 = Abbrechen): ").strip()
        if raw_ects == "0":
            print("Vorgang abgebrochen.")
            return
        ects = InputValidator.parse_int(raw_ects, "ECTS müssen eine ganze Zahl sein.")
        if ects <= 0:
            raise ValueError("ECTS müssen positiv sein.")

        assessment_name_raw = input("Name der Prüfungsleistung (z.B. Klausur, 0 = Abbrechen): ").strip()
        if assessment_name_raw == "0":
            print("Vorgang abgebrochen.")
            return
        assessment_name = assessment_name_raw.strip() or "Prüfungsleistung"

        raw_max_points = input("Maximale Punktzahl (z.B. 100, 0 = Abbrechen): ").strip().replace(",", ".")
        if raw_max_points == "0":
            print("Vorgang abgebrochen.")
            return
        max_points = InputValidator.parse_float(raw_max_points, "Maximale Punktzahl muss eine Zahl sein.")
        if max_points <= 0:
            raise ValueError("Maximale Punktzahl muss positiv sein.")

        # Neue, eindeutige Modul-ID bestimmen
        existing_ids = {m.id for m in self.program.all_modules() if m.id is not None}
        new_id = max(existing_ids) + 1 if existing_ids else 1

        assessment = Assessment(name=assessment_name, max_points=max_points)
        module = Module(id=new_id, code=code, title=title, ects=ects, assessment=assessment)
        semester.add_module(module)

        # Nach erfolgreichem Hinzufügen automatisch speichern
        PersistenceService.save(self.program, self.data_path)
        print(f"Modul {code} (ID {new_id}) wurde zu Semester {semester_number} hinzugefügt und gespeichert.\n")

    def _show_grades(self) -> None:
        snapshot = self.program.snapshot()
        # Module mit Note
        graded = [m for m in snapshot.completed_modules if m.assessment.grade is not None]
        # Anerkannte Module ohne Note
        recognized = snapshot.recognized_modules

        if not graded and not recognized:
            print("Noch keine benoteten oder anerkannten Module vorhanden.")
            return

        vm = DashboardViewModel(self.program)
        _, code_index = self._build_indexes(snapshot)

        print(vm.grade_summary())
        print("Notenübersicht (inkl. anerkannter Module):")
        # Notentabelle zeigt benotete und anerkannte Module gemeinsam an
        modules_for_overview = graded + recognized
        print(vm.module_table(modules_for_overview, id_map=code_index))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLI-Dashboard für Studienfortschritt.")
    default_data = Path(__file__).with_name("data").joinpath("sample_program.json")
    parser.add_argument(
        "--data",
        type=Path,
        default=default_data,
        help=f"Pfad zur Programmdaten-Datei (Standard: {default_data})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = args.data
    if not data_path.exists():
        raise FileNotFoundError(f"Datendatei nicht gefunden: {data_path}")
    program = PersistenceService.load(data_path)

    # Hinweis nur einmal beim Start anzeigen
    print(
        "Hinweis: In allen Eingabemasken kannst du mit '0' den aktuellen Vorgang "
        "abbrechen und ins vorherige Menü zurückkehren.\n"
    )

    cli = DashboardCLI(program, data_path)
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer.")


if __name__ == "__main__":
    main()

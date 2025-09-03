# Улучшенный генератор G-кода с расширенными возможностями

import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class MaterialGroup(Enum):
    """Группы материалов по ISO"""
    P = "P"  # Сталь
    M = "M"  # Нержавеющая сталь
    K = "K"  # Чугун
    N = "N"  # Алюминий
    S = "S"  # Титан/никелевые сплавы
    H = "H"  # Закаленная сталь

@dataclass
class Material:
    """Характеристики материала"""
    group: MaterialGroup
    grade: str
    hardness: Optional[str] = None
    notes: str = ""

@dataclass
class Tool:
    """Характеристики инструмента"""
    type: str
    diameter: float
    flutes: int
    corner_radius: float = 0.0
    insert_type: str = ""
    coating: str = ""
    holder: str = ""
    stickout: float = 0.0

@dataclass
class CuttingParams:
    """Параметры резания"""
    Vc: float  # Скорость резания, м/мин
    fz: float  # Подача на зуб, мм/зуб
    fn: float  # Подача на оборот, мм/об
    rpm: int   # Обороты шпинделя
    feed: float # Подача, мм/мин
    ap: float  # Глубина резания, мм
    ae: float  # Ширина резания, мм

class CuttingSpeedCalculator:
    """Калькулятор режимов резания"""
    
    # Оптимальные диапазоны для разных материалов
    MATERIAL_RANGES = {
        MaterialGroup.P: {"Vc": (120, 220), "fz": (0.02, 0.12)},
        MaterialGroup.M: {"Vc": (80, 180), "fz": (0.02, 0.10)},
        MaterialGroup.K: {"Vc": (160, 260), "fz": (0.03, 0.18)},
        MaterialGroup.N: {"Vc": (250, 600), "fz": (0.04, 0.25)},
        MaterialGroup.S: {"Vc": (60, 120), "fz": (0.02, 0.08)},
        MaterialGroup.H: {"Vc": (80, 150), "fz": (0.01, 0.06)}
    }
    
    @classmethod
    def calculate_milling_params(cls, material: Material, tool: Tool, 
                                operation: str = "roughing") -> CuttingParams:
        """Расчет параметров фрезерования"""
        ranges = cls.MATERIAL_RANGES.get(material.group, cls.MATERIAL_RANGES[MaterialGroup.P])
        
        # Выбор параметров в зависимости от операции
        if operation == "roughing":
            Vc = ranges["Vc"][0] + (ranges["Vc"][1] - ranges["Vc"][0]) * 0.7
            fz = ranges["fz"][0] + (ranges["fz"][1] - ranges["fz"][0]) * 0.8
        else:  # finishing
            Vc = ranges["Vc"][0] + (ranges["Vc"][1] - ranges["Vc"][0]) * 0.9
            fz = ranges["fz"][0] + (ranges["fz"][1] - ranges["fz"][0]) * 0.5
        
        # Расчет оборотов
        rpm = int(1000 * Vc / (math.pi * tool.diameter))
        
        # Расчет подачи
        feed = fz * tool.flutes * rpm
        
        # Глубина и ширина резания
        if operation == "roughing":
            ap = tool.diameter * 0.5  # 50% диаметра
            ae = tool.diameter * 0.4  # 40% диаметра
        else:
            ap = tool.diameter * 0.1  # 10% диаметра
            ae = tool.diameter * 0.2  # 20% диаметра
        
        return CuttingParams(
            Vc=Vc, fz=fz, fn=fz * tool.flutes,
            rpm=rpm, feed=feed, ap=ap, ae=ae
        )
    
    @classmethod
    def calculate_drilling_params(cls, material: Material, tool: Tool) -> CuttingParams:
        """Расчет параметров сверления"""
        ranges = cls.MATERIAL_RANGES.get(material.group, cls.MATERIAL_RANGES[MaterialGroup.P])
        
        # Для сверления используем более консервативные параметры
        Vc = ranges["Vc"][0] + (ranges["Vc"][1] - ranges["Vc"][0]) * 0.5
        fn = 0.1 + (tool.diameter * 0.02)  # Подача зависит от диаметра
        
        rpm = int(1000 * Vc / (math.pi * tool.diameter))
        feed = fn * rpm
        
        return CuttingParams(
            Vc=Vc, fz=0, fn=fn,
            rpm=rpm, feed=feed, ap=tool.diameter, ae=0
        )

class EnhancedGCodeGenerator:
    """Улучшенный генератор G-кода"""
    
    def __init__(self, controller: str = "fanuc"):
        self.controller = controller.lower()
        self.settings = self._get_controller_settings()
    
    def _get_controller_settings(self) -> Dict:
        """Настройки контроллера"""
        settings = {
            "fanuc": {
                "header": ["G90", "G17", "G21", "G40", "G49", "G80", "G54"],
                "spindle_on": "M3 S{spindle}",
                "spindle_off": "M5",
                "coolant_on": "M8",
                "coolant_off": "M9",
                "rapid": "G0",
                "linear": "G1",
                "arc_cw": "G2",
                "arc_ccw": "G3",
                "program_end": "M30",
                "drill_cycle": "G81",
                "peck_cycle": "G83",
                "dwell_cycle": "G82"
            },
            "siemens": {
                "header": ["G90", "G17", "G71", "G40", "G54"],
                "spindle_on": "M3 S{spindle}",
                "spindle_off": "M5",
                "coolant_on": "M7",
                "coolant_off": "M9",
                "rapid": "G0",
                "linear": "G1",
                "arc_cw": "G2",
                "arc_ccw": "G3",
                "program_end": "M2",
                "drill_cycle": "CYCLE81",
                "peck_cycle": "CYCLE83",
                "dwell_cycle": "CYCLE82"
            },
            "heidenhain": {
                "header": ["BEGIN PGM {name} MM"],
                "spindle_on": "SPINDLE ON CW SPEED {spindle}",
                "spindle_off": "SPINDLE OFF",
                "coolant_on": "COOLANT ON",
                "coolant_off": "COOLANT OFF",
                "rapid": "L",
                "linear": "L",
                "arc_cw": "CC",
                "arc_ccw": "C",
                "program_end": "END PGM",
                "drill_cycle": "CYCL DEF 200 DRILLING",
                "peck_cycle": "CYCL DEF 203 UNIVERSAL DRILLING",
                "dwell_cycle": "CYCL DEF 201 REAMING"
            }
        }
        return settings.get(self.controller, settings["fanuc"])
    
    def generate_adaptive_milling(self, geometry_bounds: Tuple, 
                                material: Material, tool: Tool,
                                params: Dict) -> List[str]:
        """Генерация адаптивного фрезерования"""
        cutting_params = CuttingSpeedCalculator.calculate_milling_params(
            material, tool, "roughing"
        )
        
        lines = []
        settings = self.settings
        
        # Заголовок программы
        lines.extend(settings["header"])
        lines.append(f"(Adaptive milling - {material.grade})")
        lines.append(f"(Tool: {tool.diameter}mm, {tool.flutes} flutes)")
        lines.append(f"(Vc: {cutting_params.Vc:.1f} m/min, fz: {cutting_params.fz:.3f} mm/tooth)")
        
        # Включение шпинделя и СОЖ
        lines.append(settings["spindle_on"].format(spindle=cutting_params.rpm))
        lines.append(settings["coolant_on"])
        
        # Безопасная высота
        clearance = params.get("clearance", 5.0)
        lines.append(f"{settings['rapid']} Z{clearance:.3f}")
        
        # Адаптивная траектория (упрощенная версия)
        xmin, xmax, ymin, ymax, zmin, zmax = geometry_bounds
        stepover = tool.diameter * 0.4
        
        # Спиральная траектория от центра
        center_x = (xmin + xmax) / 2
        center_y = (ymin + ymax) / 2
        max_radius = max(xmax - center_x, ymax - center_y)
        
        lines.append(f"{settings['rapid']} X{center_x:.3f} Y{center_y:.3f}")
        lines.append(f"{settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}")
        lines.append(f"F{cutting_params.feed:.1f}")
        
        # Спиральная траектория
        radius = stepover
        while radius <= max_radius:
            # Круговая траектория
            for angle in range(0, 360, 10):
                x = center_x + radius * math.cos(math.radians(angle))
                y = center_y + radius * math.sin(math.radians(angle))
                lines.append(f"{settings['linear']} X{x:.3f} Y{y:.3f}")
            radius += stepover
        
        # Отвод
        lines.append(f"{settings['rapid']} Z{clearance:.3f}")
        lines.append(settings["coolant_off"])
        lines.append(settings["spindle_off"])
        lines.append(settings["program_end"])
        
        return lines
    
    def generate_thread_milling(self, hole_center: Tuple[float, float],
                              thread_params: Dict, tool: Tool) -> List[str]:
        """Генерация резьбофрезерования"""
        lines = []
        settings = self.settings
        
        x, y = hole_center
        diameter = thread_params.get("diameter", 10.0)
        pitch = thread_params.get("pitch", 1.5)
        depth = thread_params.get("depth", 10.0)
        
        lines.extend(settings["header"])
        lines.append(f"(Thread milling - M{diameter:.0f}x{pitch:.1f})")
        
        # Параметры резьбофрезерования
        thread_diameter = diameter - pitch * 0.5
        passes = int(depth / pitch) + 1
        
        lines.append(settings["spindle_on"].format(spindle=1000))
        lines.append(settings["coolant_on"])
        
        clearance = 5.0
        lines.append(f"{settings['rapid']} Z{clearance:.3f}")
        lines.append(f"{settings['rapid']} X{x:.3f} Y{y:.3f}")
        
        # Резьбофрезерование
        for pass_num in range(passes):
            z = -pass_num * pitch
            lines.append(f"{settings['linear']} Z{z:.3f} F{100:.1f}")
            
            # Круговая интерполяция для резьбы
            if self.controller == "heidenhain":
                lines.append(f"CC X{x:.3f} Y{y:.3f} I{thread_diameter/2:.3f}")
            else:
                lines.append(f"{settings['arc_cw']} X{x:.3f} Y{y:.3f} I{thread_diameter/2:.3f} F{200:.1f}")
        
        lines.append(f"{settings['rapid']} Z{clearance:.3f}")
        lines.append(settings["coolant_off"])
        lines.append(settings["spindle_off"])
        lines.append(settings["program_end"])
        
        return lines
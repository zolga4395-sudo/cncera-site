"""
Сервис для работы с STL файлами
"""

from pathlib import Path
from typing import Dict

try:
    from stl import mesh as stlmesh
except ImportError:
    stlmesh = None

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
except ImportError:
    matplotlib = None
    plt = None

class StlService:
    """Сервис для анализа и рендеринга STL файлов"""
    
    def analyze_stl(self, stl_path: Path) -> Dict:
        """Анализ STL файла"""
        if not stlmesh:
            return {"vertices": 0, "faces": 0, "error": "numpy-stl не установлен"}
        
        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            return {
                "vertices": len(mesh.vectors) * 3,
                "faces": len(mesh.vectors),
                "volume": mesh.volume if hasattr(mesh, 'volume') else 0,
                "surface_area": mesh.areas.sum() if hasattr(mesh, 'areas') else 0
            }
        except Exception as e:
            return {"vertices": 0, "faces": 0, "error": f"Ошибка анализа STL: {str(e)}"}
    
    def render_stl_to_png(self, stl_path: Path, png_path: Path) -> bool:
        """Рендеринг STL в PNG"""
        if not matplotlib or not stlmesh or not plt:
            return False
        
        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            faces = mesh.vectors
            
            # Вычисляем центр и радиус
            xs, ys, zs = mesh.x, mesh.y, mesh.z
            cx = (xs.min() + xs.max()) / 2
            cy = (ys.min() + ys.max()) / 2
            cz = (zs.min() + zs.max()) / 2
            
            r = max(
                (xs.max() - xs.min()) / 2,
                (ys.max() - ys.min()) / 2,
                (zs.max() - zs.min()) / 2
            ) or 1.0
            
            # Создаем фигуру
            fig = plt.figure(figsize=(8, 8), dpi=150)
            ax = fig.add_subplot(111, projection="3d")
            
            # Настройка цветов
            fig.patch.set_facecolor("#0b1b24")
            ax.set_facecolor("#0b1b24")
            ax.set_proj_type("ortho")
            
            # Добавляем mesh
            collection = Poly3DCollection(faces, linewidths=0.1)
            collection.set_facecolor((0.55, 0.75, 0.95, 1.0))
            collection.set_edgecolor((0.1, 0.1, 0.15, 0.25))
            ax.add_collection3d(collection)
            
            # Настройка осей
            ax.set_xlim(cx - r, cx + r)
            ax.set_ylim(cy - r, cy + r)
            ax.set_zlim(cz - r, cz + r)
            ax.set_axis_off()
            ax.view_init(30, 45)
            
            # Сохранение
            fig.tight_layout(pad=0)
            fig.savefig(
                str(png_path), 
                transparent=False, 
                facecolor=fig.get_facecolor(),
                bbox_inches='tight',
                dpi=150
            )
            plt.close(fig)
            
            return True
            
        except Exception as e:
            try:
                plt.close("all")
            except:
                pass
            return False
    
    def get_stl_bounds(self, stl_path: Path) -> Dict:
        """Получение границ STL модели"""
        if not stlmesh:
            return {}
        
        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            
            return {
                "min_x": float(mesh.x.min()),
                "max_x": float(mesh.x.max()),
                "min_y": float(mesh.y.min()),
                "max_y": float(mesh.y.max()),
                "min_z": float(mesh.z.min()),
                "max_z": float(mesh.z.max()),
                "center_x": float((mesh.x.min() + mesh.x.max()) / 2),
                "center_y": float((mesh.y.min() + mesh.y.max()) / 2),
                "center_z": float((mesh.z.min() + mesh.z.max()) / 2),
                "size_x": float(mesh.x.max() - mesh.x.min()),
                "size_y": float(mesh.y.max() - mesh.y.min()),
                "size_z": float(mesh.z.max() - mesh.z.min())
            }
            
        except Exception as e:
            return {"error": f"Ошибка получения границ: {str(e)}"}
    
    def validate_stl(self, stl_path: Path) -> Dict:
        """Валидация STL файла"""
        if not stl_path.exists():
            return {"valid": False, "error": "Файл не существует"}
        
        if not stlmesh:
            return {"valid": False, "error": "numpy-stl не установлен"}
        
        try:
            mesh = stlmesh.Mesh.from_file(str(stl_path))
            
            # Базовые проверки
            if len(mesh.vectors) == 0:
                return {"valid": False, "error": "STL файл пустой"}
            
            # Проверка на NaN значения
            import numpy as np
            if np.any(np.isnan(mesh.vectors)):
                return {"valid": False, "error": "STL содержит некорректные координаты"}
            
            return {
                "valid": True,
                "faces": len(mesh.vectors),
                "vertices": len(mesh.vectors) * 3,
                "file_size": stl_path.stat().st_size
            }
            
        except Exception as e:
            return {"valid": False, "error": f"Ошибка валидации: {str(e)}"}
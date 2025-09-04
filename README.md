# CNCera - 3D Analysis & G-code Generation

CNCera is a web-based application for 3D model analysis and G-code generation for CNC machining. It supports STEP and STL file formats and can generate G-code for various CNC controllers and operation types.

## Features

- **3D Model Analysis**: Upload and analyze STEP (.step, .stp) and STL files
- **Interactive 3D Viewer**: Built with Three.js for real-time 3D visualization
- **G-code Generation**: Support for multiple CNC controllers (Fanuc, Siemens, Heidenhain, GSK, Mazak)
- **Multiple Operation Types**: Milling, turning, drilling, chamfering, roughing, and finishing
- **Advanced CAM Features**: Waterline machining, stepdown operations, custom allowances
- **Modern UI**: Responsive design with Tailwind CSS

## Project Structure

```
cncera/
├── backend/
│   ├── app.py              # Main Flask application
│   └── gcode_generator.py  # G-code generation functions
├── frontend/
│   └── index.html          # Main HTML template
├── static/
│   ├── style.css           # Custom CSS styles
│   └── app.js              # Frontend JavaScript
├── models/                 # Generated STL files
├── temp/                   # Temporary files
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Installation

### Prerequisites

- Python 3.8 or higher
- FreeCAD (for STEP file processing)
- Modern web browser

### Setup

1. **Clone or download the project files**

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FreeCAD**:
   - **Windows**: Download from [FreeCAD website](https://www.freecadweb.org/downloads.php)
   - **Linux**: `sudo apt-get install freecad` or `sudo yum install freecad`
   - **macOS**: `brew install freecad` or download from website

4. **Set FreeCAD path** (optional):
   ```bash
   export FREECADCMD_PATH="/path/to/FreeCADCmd"
   ```

### Running the Application

1. **Start the Flask server**:
   ```bash
   cd backend
   python app.py
   ```

2. **Open your browser** and navigate to:
   ```
   http://127.0.0.1:5000
   ```

## Usage

### 1. Upload and Analyze Model

1. Select a STEP (.step, .stp) or STL file
2. Choose units (auto, mm, inch, m)
3. Adjust meshing parameters:
   - Linear Deflection: Controls mesh density
   - Angular Deflection: Controls surface smoothness
   - Relative: Use relative deflection
4. Click "Анализировать" (Analyze)

### 2. Generate G-code

1. Select CNC controller (Fanuc, Siemens, Heidenhain, GSK, Mazak)
2. Choose operation type:
   - **Milling**: 3D milling operations
   - **Turning**: Lathe operations
   - **Drilling**: Drilling cycles
   - **Chamfer**: Edge chamfering
   - **Roughing**: Rough machining
   - **Finishing**: Finish machining

3. Configure tool parameters:
   - Tool diameter
   - Spindle speed
   - Feed rates
   - Clearance height

4. Set operation-specific parameters:
   - **Milling**: Stepover, stepdown, waterline options
   - **Turning**: Workpiece diameter, cut depth, feed per revolution
   - **Drilling**: Drill diameter, depth, cycle type

5. Adjust allowances if needed
6. Click "Сгенерировать G-код" (Generate G-code)

## Supported Controllers

- **Fanuc**: Standard G-code with M3/M5, G0/G1
- **Siemens**: G71 metric, M7 coolant
- **Heidenhain**: Conversational programming style
- **GSK**: G00/G01 format
- **Mazak**: M99 program end

## File Formats

### Input
- **STEP**: .step, .stp files (requires FreeCAD)
- **STL**: .stl files (direct processing)

### Output
- **STL**: Converted mesh files
- **G-code**: .nc files for CNC machines
- **JSON**: Analysis results

## Advanced Features

### Waterline Machining
- Generates contour paths at specified Z levels
- Useful for complex 3D surfaces
- Configurable step height

### Stepdown Operations
- Multi-level roughing passes
- Reduces tool load and improves surface finish
- Automatic level calculation

### Custom Allowances
- Manual adjustment of machining boundaries
- Positive/negative allowances supported
- Separate X, Y, Z axis control

## Troubleshooting

### Common Issues

1. **FreeCAD not found**:
   - Install FreeCAD and add to PATH
   - Set FREECADCMD_PATH environment variable

2. **Large file processing**:
   - Increase meshing parameters for faster processing
   - Files limited to 100MB

3. **3D viewer not loading**:
   - Check internet connection (loads Three.js from CDN)
   - PNG preview will be shown as fallback

### Performance Tips

- Use appropriate meshing parameters for your model complexity
- Smaller stepover values increase processing time
- Waterline operations can be computationally intensive

## Development

### Backend Structure
- `app.py`: Flask routes and file handling
- `gcode_generator.py`: CAM algorithms and G-code generation

### Frontend Structure
- `index.html`: Main interface
- `app.js`: Client-side logic and 3D viewer
- `style.css`: Custom styling

### Adding New Controllers
Edit `get_controller_settings()` in `gcode_generator.py` to add new controller support.

### Adding New Operations
Create new functions in `gcode_generator.py` following the existing pattern.

## License

This project is open source. Please check the license terms for commercial use.

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## Support

For technical support or questions, please create an issue in the project repository.
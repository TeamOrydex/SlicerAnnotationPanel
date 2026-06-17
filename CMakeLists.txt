cmake_minimum_required(VERSION 3.16.3...3.27.7 FATAL_ERROR)

project(SlicerAnnotationPanel)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE    "https://github.com/TeamOrydex/SlicerAnnotationPanel")
set(EXTENSION_CATEGORY    "Quantification")
set(EXTENSION_CONTRIBUTORS "saad-orydex (Orydex)")
set(EXTENSION_DESCRIPTION
  "Annotation Panel is a 3D Slicer extension that brings classification, ROI, and segmentation annotation into one preset-driven workflow with portable export packages.")
set(EXTENSION_ICONURL     "https://raw.githubusercontent.com/TeamOrydex/SlicerAnnotationPanel/production/AnnotationPanel/Resources/Icons/AnnotationPanel.png")
set(EXTENSION_SCREENSHOTURLS
  "https://raw.githubusercontent.com/TeamOrydex/SlicerAnnotationPanel/production/static/import-and-resume.png")
set(EXTENSION_DEPENDS     "NA")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(AnnotationPanel)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})

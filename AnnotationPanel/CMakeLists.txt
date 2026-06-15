cmake_minimum_required(VERSION 3.16.3...3.27.7 FATAL_ERROR)

project(AnnotationPanel)

#-----------------------------------------------------------------------------
set(KIT_PYTHON_SCRIPTS
  AnnotationPanel.py
)

set(KIT_PYTHON_RESOURCES
)

ctkMacroCompilePythonScript(
  TARGET_NAME AnnotationPanel
  SCRIPTS "${KIT_PYTHON_SCRIPTS}"
  RESOURCES "${KIT_PYTHON_RESOURCES}"
  DESTINATION_DIR ${CMAKE_BINARY_DIR}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}
  INSTALL_DIR ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}
)

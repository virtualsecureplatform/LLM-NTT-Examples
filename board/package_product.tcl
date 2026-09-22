# Vivado 2023.2 package_xo flow; stream interfaces are inferred by IP packager.
set part [lindex $argv 0]
create_project product_pack ./pack_project -part $part
add_files -norecurse [list SearchTop.sv product_stream.sv]
set_property top ProductStream [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir ./ip -vendor llmntt.org -library research -taxonomy /KernelIP -import_files
set core [ipx::current_core]
set_property name ProductStream $core
set_property sdx_kernel true $core
set_property sdx_kernel_type rtl $core
foreach interface {s_axis m_axis} {
    ipx::associate_bus_interfaces -busif $interface -clock ap_clk $core
}
set_property value ap_rst_n [ipx::add_bus_parameter ASSOCIATED_RESET [ipx::get_bus_interfaces ap_clk -of_objects $core]]
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity -kernel $core
ipx::save_core $core
package_xo -xo_path ProductStream.xo -kernel_name ProductStream -ctrl_protocol ap_ctrl_none -ip_directory ./ip -output_kernel_xml kernel.xml
close_project

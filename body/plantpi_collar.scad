// ============================================================
// PlantPi Collar / Bulkhead Ring
// Replaces stock lid on Eagle 1623BLK 20-gal drum
// Seats on drum rim, sealed by existing lever-lock band
// 8 umbilical ports evenly spaced around perimeter
// ============================================================

// --- KEY DIMENSIONS (all in mm) ---

// Eagle 1623BLK drum top inner diameter: 15.375" = 390.525mm
drum_id_top       = 390.525;
// Drum wall thickness estimate (HDPE blow-molded, ~3-4mm)
drum_wall         = 4.0;
// Drum outer diameter at rim
drum_od_top       = drum_id_top + 2 * drum_wall; // ~398.5mm

// Collar parameters
collar_od         = drum_id_top - 0.5;  // slight clearance to sit inside rim
collar_id         = drum_id_top - 20;   // 10mm wall thickness
collar_height     = 40;                 // total height of collar ring
collar_lip_width  = 15;                 // lip that overhangs drum rim
collar_lip_thick  = 5;                  // thickness of the overhang lip

// Gasket channel on bottom face (for silicone O-ring)
gasket_channel_w  = 3.0;
gasket_channel_d  = 2.5;
gasket_channel_r  = (collar_od/2 + collar_id/2) / 2; // centered in wall

// Top plate (seals electronics from water)
top_plate_thick   = 4.0;

// --- UMBILICAL PORT PARAMETERS ---
num_ports         = 8;

// Port hole layout (each port is a cluster of holes)
// Pump tube: barbed grommet hole
pump_hole_dia     = 12.0;   // ~3/8" ID barb + clearance
// Soil sensor connectors: JST-XH 3-pin (~7.5 x 5.8mm)
sensor_slot_w     = 8.0;
sensor_slot_h     = 6.5;
// ARGB LED connector: JST-SM 3-pin (~9.5 x 5mm) 
led_slot_w        = 10.0;
led_slot_h        = 5.5;

// Port cluster positioning
port_radial_pos   = collar_od/2 - 2;  // center of ports, near outer wall
port_vertical_pos = collar_height / 2; // centered vertically in collar wall

// Spacing within each port cluster (angular offset in degrees)
// Each port cluster spans ~30° of the collar circumference
// Sub-elements offset within that arc
pump_offset_angle    = -6;  // degrees from port center
sensor1_offset_angle = -2;
sensor2_offset_angle = 2;
led_offset_angle     = 6;

// --- SQUID TENTACLE GUIDES ---
tentacle_length   = 30;     // how far the guide curves extend below collar
tentacle_od       = 35;     // outer diameter of the tube guide
tentacle_id       = 26;     // inner diameter (fits 1.25" OD PVC = 31.75mm with squeeze)

// --- PRINT SEGMENTATION ---
// Collar is ~390mm diameter, too large for most printers
// Split into segments that bolt together
num_segments      = 4;      // quarter-circle segments
bolt_hole_dia     = 4.5;    // M4 bolt clearance
bolt_tab_width    = 12;
bolt_tab_length   = 20;

// --- RESOLUTION ---
$fn = 120;

// ============================================================
// MODULES
// ============================================================

// Single port cluster cutout (to be subtracted from collar wall)
module port_cutout() {
    // Pump tube hole
    rotate([0, 0, pump_offset_angle])
        translate([port_radial_pos, 0, port_vertical_pos])
            rotate([0, 90, 0])
                cylinder(d=pump_hole_dia, h=30, center=true);
    
    // Soil sensor 1 (top) - rectangular slot
    rotate([0, 0, sensor1_offset_angle])
        translate([port_radial_pos, 0, port_vertical_pos])
            rotate([0, 90, 0])
                cube([sensor_slot_h, sensor_slot_w, 30], center=true);
    
    // Soil sensor 2 (bottom) - rectangular slot
    rotate([0, 0, sensor2_offset_angle])
        translate([port_radial_pos, 0, port_vertical_pos])
            rotate([0, 90, 0])
                cube([sensor_slot_h, sensor_slot_w, 30], center=true);
    
    // ARGB LED connector slot
    rotate([0, 0, led_offset_angle])
        translate([port_radial_pos, 0, port_vertical_pos])
            rotate([0, 90, 0])
                cube([led_slot_h, led_slot_w, 30], center=true);
}

// All port cutouts arranged around the collar
module all_port_cutouts() {
    for (i = [0 : num_ports - 1]) {
        rotate([0, 0, i * (360 / num_ports)])
            port_cutout();
    }
}

// Tentacle guide - a curved tube guide extending below the collar
module tentacle_guide() {
    translate([0, 0, -tentacle_length])
        difference() {
            // Outer shape - slightly tapered cylinder with rounded end
            hull() {
                cylinder(d=tentacle_od, h=1);
                translate([0, 0, tentacle_length])
                    cylinder(d=tentacle_od + 4, h=1);
            }
            // Inner bore for the PVC umbilical tube
            translate([0, 0, -1])
                cylinder(d=tentacle_id, h=tentacle_length + 10);
        }
}

// All tentacle guides around the collar
module all_tentacle_guides() {
    for (i = [0 : num_ports - 1]) {
        rotate([0, 0, i * (360 / num_ports)])
            translate([port_radial_pos, 0, 0])
                tentacle_guide();
    }
}

// Gasket channel ring (subtracted from bottom face)
module gasket_channel() {
    translate([0, 0, -0.01])
        difference() {
            cylinder(r=gasket_channel_r + gasket_channel_w/2, h=gasket_channel_d);
            translate([0, 0, -0.1])
                cylinder(r=gasket_channel_r - gasket_channel_w/2, h=gasket_channel_d + 0.2);
        }
}

// Bolt tabs at segment joins
module bolt_tabs() {
    for (i = [0 : num_segments - 1]) {
        angle = i * (360 / num_segments);
        // Tab on the inner wall at each segment boundary
        rotate([0, 0, angle])
            translate([collar_id/2 - 2, -bolt_tab_width/2, 0])
                difference() {
                    cube([bolt_tab_length, bolt_tab_width, collar_height]);
                    // Two bolt holes per tab
                    translate([bolt_tab_length/2, bolt_tab_width/2, collar_height * 0.25])
                        cylinder(d=bolt_hole_dia, h=collar_height);
                    translate([bolt_tab_length/2, bolt_tab_width/2, collar_height * 0.75])
                        cylinder(d=bolt_hole_dia, h=collar_height);
                }
    }
}

// Main collar body
module collar_body() {
    difference() {
        union() {
            // Main collar ring
            difference() {
                cylinder(d=collar_od, h=collar_height);
                translate([0, 0, -0.1])
                    cylinder(d=collar_id, h=collar_height + 0.2);
            }
            
            // Overhanging lip (sits on top of drum rim)
            translate([0, 0, collar_height - collar_lip_thick])
                difference() {
                    cylinder(d=collar_od + 2 * collar_lip_width, h=collar_lip_thick);
                    translate([0, 0, -0.1])
                        cylinder(d=collar_id, h=collar_lip_thick + 0.2);
                }
            
            // Top plate (sealed surface)
            translate([0, 0, collar_height - collar_lip_thick - top_plate_thick])
                cylinder(d=collar_id + 0.2, h=top_plate_thick);
        }
        
        // Subtract port cutouts
        all_port_cutouts();
        
        // Subtract gasket channel from bottom
        gasket_channel();
    }
}

// Segment cut tool - isolates one printable segment
module segment_cut(seg_index) {
    seg_angle = 360 / num_segments;
    start_angle = seg_index * seg_angle;
    
    intersection() {
        // Full collar with tentacles
        union() {
            collar_body();
            all_tentacle_guides();
            bolt_tabs();
        }
        
        // Pie-slice selector
        translate([0, 0, -tentacle_length - 10])
            linear_extrude(height = collar_height + tentacle_length + 20)
                polygon([
                    [0, 0],
                    [300 * cos(start_angle), 300 * sin(start_angle)],
                    [300 * cos(start_angle + seg_angle/3), 300 * sin(start_angle + seg_angle/3)],
                    [300 * cos(start_angle + 2*seg_angle/3), 300 * sin(start_angle + 2*seg_angle/3)],
                    [300 * cos(start_angle + seg_angle), 300 * sin(start_angle + seg_angle)]
                ]);
    }
}

// ============================================================
// RENDER OPTIONS - uncomment what you want to see
// ============================================================

// Full assembled collar (for visualization)
color("DimGray") collar_body();
color("DarkSlateGray") all_tentacle_guides();

// Individual printable segment (uncomment to export):
// segment_cut(0);  // Segment 1 of 4
// segment_cut(1);  // Segment 2 of 4
// segment_cut(2);  // Segment 3 of 4
// segment_cut(3);  // Segment 4 of 4

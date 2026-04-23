// ============================================================
// PlantPi Squid Head - Pi Housing
// Sits atop the collar/bulkhead ring
// Contains Pi 4, relay, ADC, wiring
// 7" touchscreen angled on front face
// Subtle squid aesthetic with eyes flanking screen
// Hinged lid for access
// ============================================================

// --- KEY DIMENSIONS (all in mm) ---

// Must match collar inner diameter for seating
collar_id         = 370.525;  // from collar model (drum_id - 20)

// Housing base - sits on top of collar's top plate
// Doesn't need to be as wide as the collar
housing_base_dia  = 220;      // housing is smaller, centered on collar
housing_height    = 140;      // total height of squid head body
housing_wall      = 3.5;      // wall thickness

// Squid mantle taper
mantle_top_dia    = 160;      // narrower at the top for squid shape
mantle_dome_r     = 40;       // radius of the dome on top

// --- TOUCHSCREEN CUTOUT ---
// Official Raspberry Pi 7" touchscreen
// Active area: 155 x 86mm
// Board dimensions: ~194 x 110mm  
// We'll make the visible cutout for the active area
// and mounting posts for the board
screen_active_w   = 155;
screen_active_h   = 86;
screen_board_w    = 194;
screen_board_h    = 110;
screen_board_d    = 8;        // depth/thickness of screen assembly

// Screen angle from vertical (tilted back for viewing)
screen_tilt       = 15;       // degrees from vertical

// Screen position on the front face
screen_center_z   = housing_height * 0.5;  // vertical center on housing

// Screen bezel (frame around cutout)
screen_bezel      = 8;

// --- SQUID EYES ---
eye_diameter      = 25;
eye_depth         = 4;        // how far they protrude
eye_pupil_dia     = 10;
// Eyes positioned flanking the screen
eye_offset_x      = screen_active_w / 2 + 30;  // distance from center
eye_offset_z      = screen_center_z + 15;       // slightly above screen center

// --- PI 4 MOUNTING ---
// Pi 4 board: 85 x 56mm, mounting holes on 58 x 49mm pattern
pi_board_w        = 85;
pi_board_l        = 56;
pi_mount_w        = 58;       // hole-to-hole width
pi_mount_l        = 49;       // hole-to-hole length
pi_standoff_h     = 8;        // clearance under board
pi_mount_hole_d   = 2.75;     // M2.5 clearance

// --- HINGE AND LID ---
// Lid splits the housing roughly 60% up
lid_split_z       = housing_height * 0.65;
hinge_pin_dia     = 3.0;      // M3 rod or filament as hinge pin
hinge_barrel_od   = 8.0;
hinge_barrel_len  = 15;
num_hinge_knuckles = 5;       // alternating knuckles for print-in-place style

// Lid latch (front, below screen)
latch_width       = 20;
latch_height      = 8;
latch_hook_depth  = 2;

// --- MOUNTING FLANGE ---
// Flange that bolts or sits onto the collar top plate
flange_od         = housing_base_dia + 30;
flange_thick      = 4;
flange_bolt_dia   = 4.5;      // M4 clearance
flange_bolt_circle = housing_base_dia / 2 + 8;
num_flange_bolts  = 6;

// --- CABLE PASS-THROUGHS ---
// Holes in the base for wires from collar ports to reach the Pi
cable_pass_dia    = 8;
num_cable_passes  = 8;
cable_pass_circle = housing_base_dia / 2 - 20;

// --- PRINT SEGMENTATION ---
// Housing is ~220mm diameter - fits on 256mm bed as one piece
// But we'll split into base + lid at the hinge line
// Each can print separately

// --- RESOLUTION ---
$fn = 120;

// ============================================================
// MODULES
// ============================================================

// Squid mantle profile - tapered cylinder with dome
module mantle_outer() {
    hull() {
        // Base cylinder
        cylinder(d=housing_base_dia, h=1);
        // Mid section - slight bulge for organic shape
        translate([0, 0, housing_height * 0.4])
            cylinder(d=housing_base_dia + 10, h=1);
        // Upper taper
        translate([0, 0, housing_height * 0.8])
            cylinder(d=mantle_top_dia, h=1);
        // Dome top
        translate([0, 0, housing_height])
            sphere(d=mantle_top_dia * 0.8);
    }
}

module mantle_inner() {
    hull() {
        translate([0, 0, flange_thick])
            cylinder(d=housing_base_dia - 2*housing_wall, h=1);
        translate([0, 0, housing_height * 0.4])
            cylinder(d=housing_base_dia + 10 - 2*housing_wall, h=1);
        translate([0, 0, housing_height * 0.8])
            cylinder(d=mantle_top_dia - 2*housing_wall, h=1);
        translate([0, 0, housing_height])
            sphere(d=mantle_top_dia * 0.8 - 2*housing_wall);
    }
}

// Screen cutout (angled into the front face)
module screen_cutout() {
    translate([0, -housing_base_dia/2 - 5, screen_center_z])
        rotate([90 - screen_tilt, 0, 0])
            translate([0, 0, -housing_wall - 10]) {
                // Active area cutout (goes all the way through)
                cube([screen_active_w, screen_active_h, housing_wall + 30], center=true);
            }
}

// Screen bezel frame (decorative raised frame around screen)
module screen_bezel_frame() {
    translate([0, -housing_base_dia/2 + housing_wall/2, screen_center_z])
        rotate([90 - screen_tilt, 0, 0])
            difference() {
                // Outer bezel
                cube([screen_active_w + 2*screen_bezel, 
                      screen_active_h + 2*screen_bezel, 
                      3], center=true);
                // Inner cutout
                cube([screen_active_w, screen_active_h, 10], center=true);
            }
}

// Screen mounting posts (inside housing)
module screen_mount_posts() {
    // 4 posts at corners of the screen board
    for (x = [-screen_board_w/2 + 5, screen_board_w/2 - 5])
        for (z = [-screen_board_h/2 + 5, screen_board_h/2 - 5])
            translate([x, -housing_base_dia/2 + housing_wall + screen_board_d + 5, 
                       screen_center_z + z])
                rotate([90 - screen_tilt, 0, 0])
                    difference() {
                        cylinder(d=6, h=screen_board_d);
                        translate([0, 0, -0.1])
                            cylinder(d=pi_mount_hole_d, h=screen_board_d + 1);
                    }
}

// Squid eye (subtle, slightly raised)
module squid_eye(is_right=true) {
    mirror_x = is_right ? 1 : -1;
    
    translate([mirror_x * eye_offset_x, -housing_base_dia/2 + 5, eye_offset_z])
        rotate([90, 0, 0]) {
            // Outer eye - raised dome
            difference() {
                scale([1, 1, 0.4])
                    sphere(d=eye_diameter);
                // Flatten the back
                translate([0, 0, -eye_diameter])
                    cube(eye_diameter * 2, center=true);
            }
            // Pupil indent
            translate([0, 0, eye_depth - 1])
                scale([1, 1, 0.3])
                    sphere(d=eye_pupil_dia);
        }
}

// Pi 4 mounting posts
module pi_mount_posts() {
    for (x = [-pi_mount_w/2, pi_mount_w/2])
        for (y = [-pi_mount_l/2, pi_mount_l/2])
            translate([x, y, flange_thick])
                difference() {
                    cylinder(d=6, h=pi_standoff_h);
                    translate([0, 0, -0.1])
                        cylinder(d=pi_mount_hole_d, h=pi_standoff_h + 1);
                }
}

// Mounting flange base
module mounting_flange() {
    difference() {
        cylinder(d=flange_od, h=flange_thick);
        // Bolt holes
        for (i = [0 : num_flange_bolts - 1])
            rotate([0, 0, i * (360 / num_flange_bolts)])
                translate([flange_bolt_circle, 0, -0.1])
                    cylinder(d=flange_bolt_dia, h=flange_thick + 0.2);
    }
}

// Cable pass-through holes in the base
module cable_pass_throughs() {
    for (i = [0 : num_cable_passes - 1])
        rotate([0, 0, i * (360 / num_cable_passes)])
            translate([cable_pass_circle, 0, -0.1])
                cylinder(d=cable_pass_dia, h=flange_thick + 0.2);
}

// Hinge barrels on the back
module hinge_barrels(is_lid=false) {
    knuckle_len = hinge_barrel_len;
    total_len = num_hinge_knuckles * knuckle_len;
    
    translate([0, housing_base_dia/2 - 5, lid_split_z])
        rotate([0, 90, 0])
            translate([-0, 0, -total_len/2])
                for (i = [0 : num_hinge_knuckles - 1]) {
                    // Alternate knuckles between base and lid
                    if ((i % 2 == 0) != is_lid)
                        translate([0, 0, i * knuckle_len])
                            difference() {
                                cylinder(d=hinge_barrel_od, h=knuckle_len - 0.3);
                                translate([0, 0, -0.1])
                                    cylinder(d=hinge_pin_dia + 0.3, h=knuckle_len + 0.2);
                            }
                }
}

// Latch hook on front
module latch_hook() {
    translate([-latch_width/2, -housing_base_dia/2 + housing_wall - 2, lid_split_z - latch_height])
        cube([latch_width, latch_hook_depth, latch_height]);
}

module latch_catch() {
    translate([-latch_width/2, -housing_base_dia/2 + housing_wall - 2, lid_split_z])
        cube([latch_width, latch_hook_depth + 1, 3]);
}

// ============================================================
// ASSEMBLY
// ============================================================

// --- LOWER BODY (base half, prints upside down) ---
module lower_body() {
    difference() {
        union() {
            // Mantle shell
            difference() {
                mantle_outer();
                mantle_inner();
                // Cut away everything above the split line
                translate([0, 0, lid_split_z])
                    cylinder(d=500, h=200);
            }
            
            // Mounting flange
            mounting_flange();
            
            // Screen bezel
            screen_bezel_frame();
            
            // Squid eyes
            squid_eye(true);
            squid_eye(false);
            
            // Pi mounting posts
            pi_mount_posts();
            
            // Hinge barrels (base side)
            hinge_barrels(false);
            
            // Latch catch
            latch_catch();
        }
        
        // Screen cutout
        screen_cutout();
        
        // Cable pass-throughs
        cable_pass_throughs();
        
        // Ventilation slots on back (subtle)
        for (z = [flange_thick + 15 : 8 : lid_split_z - 10])
            translate([-30, housing_base_dia/2 - housing_wall - 1, z])
                cube([60, housing_wall + 2, 3]);
    }
}

// --- UPPER BODY / LID (dome half) ---
module lid() {
    difference() {
        union() {
            // Upper mantle shell
            difference() {
                mantle_outer();
                mantle_inner();
                // Cut away everything below the split line
                translate([0, 0, -1])
                    cylinder(d=500, h=lid_split_z + 1);
            }
            
            // Hinge barrels (lid side)
            hinge_barrels(true);
            
            // Latch hook
            translate([0, 0, lid_split_z])
                latch_hook();
            
            // Inner lip for alignment
            translate([0, 0, lid_split_z - 3])
                difference() {
                    cylinder(d=housing_base_dia - 2*housing_wall - 0.5, h=3);
                    translate([0, 0, -0.1])
                        cylinder(d=housing_base_dia - 2*housing_wall - 5, h=3.2);
                }
        }
    }
}

// ============================================================
// RENDER OPTIONS - uncomment what you want to see
// ============================================================

// Full assembled view
color("DimGray", 0.9) lower_body();
color("DimGray", 0.5) lid();  // semi-transparent to see inside

// For printing, uncomment one at a time:
// lower_body();
// lid();

// To see just the mounting flange:
// mounting_flange();

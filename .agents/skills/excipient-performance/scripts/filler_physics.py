"""Filler mechanism primitives, SI units. No ingredient-name coefficients.

Geometry and instantaneous flux are derived relations. Competitive occupancy
is a proposed closure, not a validated pharmaceutical constitutive law.
No function infers missing material properties or writes project state.
"""
import math
from scipy.optimize import brentq


def positive(**values):
    for key, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} must be finite and positive')


def fraction(value):
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('fraction must be in [0,1]')
    return value


def d32_from_mass_bins(diameters_m, mass_fractions):
    """Same-density spherical particles; mass/volume fractions, not counts."""
    if not diameters_m or len(diameters_m) != len(mass_fractions):
        raise ValueError('nonempty matching bins required')
    if not math.isclose(sum(mass_fractions), 1, abs_tol=1e-9):
        raise ValueError('mass fractions must sum to one')
    for d, w in zip(diameters_m, mass_fractions):
        positive(d=d)
        fraction(w)
    return 1 / sum(w / d for w, d in zip(mass_fractions, diameters_m))


def surface_m2(mass_kg, density_kg_m3, d32_m):
    """External geometric area of dense spheres; not BET pore area."""
    positive(density=density_kg_m3, d32=d32_m)
    if not math.isfinite(mass_kg) or mass_kg < 0:
        raise ValueError('mass must be nonnegative')
    return 6 * mass_kg / (density_kg_m3 * d32_m)


def capacity_ratio(carrier_mass_kg, carrier_density, carrier_d32_m,
                   accessible_fraction, api_mass_kg, api_density, api_d32_m):
    """Monolayer footprint capacity; requires API << host size and spherical API.

    Accessible fraction includes unusable geometric area and footprint packing;
    it is not inferred from Carr index. API footprint = external API area / 4.
    """
    positive(api_mass=api_mass_kg)
    area = surface_m2(carrier_mass_kg, carrier_density, carrier_d32_m)
    footprint = surface_m2(api_mass_kg, api_density, api_d32_m) / 4
    return fraction(accessible_fraction) * area / footprint


def equilibrium_occupancy(capacities, detachment_capture_ratios):
    """Candidate finite-site closure: f_i=Gamma_i*u/(K_i+u), u+sum(f_i)=1.

    u is unhosted API mass fraction, NOT automatically agglomerated API.
    Applies to monodisperse/equal-footprint API and ideal independent sites.
    Positive K required; zero K limit may have nonunique carrier allocation.
    """
    if len(capacities) != len(detachment_capture_ratios):
        raise ValueError('matching carrier parameter arrays required')
    for g, k in zip(capacities, detachment_capture_ratios):
        if not math.isfinite(g) or g < 0:
            raise ValueError('capacity must be nonnegative')
        positive(K=k)
    def hosted(u):
        return [g*u/(k+u) for g, k in zip(capacities, detachment_capture_ratios)]
    u = brentq(lambda u: u + sum(hosted(u)) - 1, 0, 1, xtol=1e-14)
    return {'unhosted_fraction': u, 'hosted_fractions': hosted(u)}


def wet_primary_fraction(occupancy, release_as_primary, unhosted_primary):
    """Measured/declared post-wetting primary fractions, at a specified time.
    Host occupation is not equated to complete release or dispersion.
    """
    fs = occupancy['hosted_fractions']
    u = occupancy['unhosted_fraction']
    if len(fs) != len(release_as_primary):
        raise ValueError('matching release fractions required')
    if not math.isclose(u+sum(fs), 1, abs_tol=1e-9):
        raise ValueError('API fractions must conserve mass')
    return fraction(u)*fraction(unhosted_primary) + sum(
        fraction(f)*fraction(p) for f,p in zip(fs, release_as_primary))


def porosity(masses_kg, solid_densities, bed_volume_m3):
    positive(volume=bed_volume_m3)
    if not masses_kg or len(masses_kg) != len(solid_densities):
        raise ValueError('nonempty matching materials required')
    volumes=[]
    for m,rho in zip(masses_kg,solid_densities):
        positive(mass=m,density=rho)
        volumes.append(m/rho)
    eps=1-sum(volumes)/bed_volume_m3
    if not 0 < eps < 1:
        raise ValueError('inconsistent bed volume and solid volumes')
    return eps


def penetration_coefficient(permeability_m2, pore_radius_m, porosity_value,
                            viscosity_pa_s, tension_n_m, contact_angle_deg):
    """l^2=B*t, B[m2/s]; rigid homogeneous bed, no imposed pressure/gravity.
    Non-wetting returns 0 for THIS spontaneous capillary mechanism only.
    """
    positive(k=permeability_m2, r=pore_radius_m, mu=viscosity_pa_s,
             gamma=tension_n_m)
    if not 0 < porosity_value < 1 or not 0 <= contact_angle_deg <= 180:
        raise ValueError('invalid porosity or contact angle')
    cosine = 0 if contact_angle_deg >= 90 else math.cos(math.radians(contact_angle_deg))
    return 4*permeability_m2*tension_n_m*cosine/(
        viscosity_pa_s*porosity_value*pore_radius_m)


def normalized_area(primary_fraction, aggregate_diameter_ratio):
    """Dense, impermeable spherical agglomerates, same API density.
    A / A_all_primary = f + (1-f)/R; R=d_agglomerate/d_primary.
    Not valid for porous penetrated/fractal aggregates without amendment.
    """
    fraction(primary_fraction)
    if not math.isfinite(aggregate_diameter_ratio) or aggregate_diameter_ratio < 1:
        raise ValueError('aggregate diameter ratio must be >=1')
    return primary_fraction+(1-primary_fraction)/aggregate_diameter_ratio


def instantaneous_flux_kg_s(mass_kg, density, primary_d32_m,
                            primary_fraction, aggregate_diameter_ratio,
                            wet_fraction, diffusion_m2_s, layer_m,
                            solubility_kg_m3, bulk_concentration_kg_m3):
    """Initial/local flux, no full-time curve or dissolution-capacity solver.
    Uniform film and Cs assumed; unsaturated bulk. API mass is remaining solid.
    """
    positive(D=diffusion_m2_s,h=layer_m,Cs=solubility_kg_m3)
    if not math.isfinite(bulk_concentration_kg_m3) or bulk_concentration_kg_m3 < 0:
        raise ValueError('bulk concentration must be nonnegative')
    area=surface_m2(mass_kg,density,primary_d32_m)*normalized_area(
        primary_fraction,aggregate_diameter_ratio)*fraction(wet_fraction)
    return diffusion_m2_s/layer_m*area*max(0,solubility_kg_m3-bulk_concentration_kg_m3)

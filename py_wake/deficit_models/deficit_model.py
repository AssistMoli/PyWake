from abc import ABC, abstractmethod
from py_wake import np
from numpy import newaxis as na
from py_wake.utils.gradients import cabs
from py_wake.utils.model_utils import method_args, RotorAvgAndGroundModelContainer
from py_wake.superposition_models import WeightedSum


class DeficitModel(ABC, RotorAvgAndGroundModelContainer):
    deficit_initalized = False

    def __init__(self, rotorAvgModel=None, groundModel=None, use_effective_ws=True, use_effective_ti=False):
        RotorAvgAndGroundModelContainer.__init__(self, rotorAvgModel=rotorAvgModel, groundModel=groundModel)

        self.WS_key = ['WS_ilk', 'WS_eff_ilk'][use_effective_ws]
        self.TI_key = ['TI_ilk', 'TI_eff_ilk'][use_effective_ti]

    @property
    def additional_args(self):
        return {self.WS_key, self.TI_key}

    @property
    def args4deficit(self):
        args4deficit = RotorAvgAndGroundModelContainer.args4model.fget(self)  # @UndefinedVariable
        args4deficit |= method_args(self.calc_deficit)
        args4deficit |= method_args(self.calc_deficit_downwind)
        args4deficit |= method_args(self._calc_layout_terms)
        args4deficit |= self.additional_args

        return args4deficit

    def _calc_layout_terms(self, **_):
        """Calculate layout dependent terms, which is not updated during simulation"""

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k not in {'layout_factor_ijlk', 'denominator_ijlk'}}

    @abstractmethod
    def calc_deficit(self):
        """Calculate wake deficit caused by the x'th most upstream wind turbines
        for all wind directions(l) and wind speeds(k) on a set of points(j)

        This method must be overridden by subclass

        See documentation of EngineeringWindFarmModel for a list of available input arguments

        Returns
        -------
        deficit_jlk : array_like
        """

    def calc_deficit_downwind(self, yaw_ilk, **kwargs):
        if np.any(yaw_ilk != 0):
            deficit_normal = self.calc_deficit(yaw_ilk=yaw_ilk, **kwargs)
            return deficit_normal
            return np.cos(yaw_ilk[:, na]) * deficit_normal
        else:
            return self.calc_deficit(yaw_ilk=yaw_ilk, **kwargs)

    def __call__(self, **kwargs):
        return self.wrap(self.calc_deficit_downwind)(**kwargs)

    def calc_layout_terms(self, **kwargs):
        return self.wrap(self._calc_layout_terms, '_calc_layout_terms')(**kwargs)


class WakeRadiusTopHat():
    """Super class of Models with a tophat shapt limited by the wake radius, e.g. NOJDeficit, GCLTurbulence etc"""


class BlockageDeficitModel(DeficitModel):
    def __init__(self, upstream_only=False, superpositionModel=None, rotorAvgModel=None, groundModel=None):
        """Parameters
        ----------
        upstream_only : bool, optional
            if true, downstream deficit from this model is set to zero
        superpositionModel : SuperpositionModel or None
            Superposition model used to sum blockage deficit.
            If None, the superposition model of the wind farm model is used
        """
        DeficitModel.__init__(self, rotorAvgModel=rotorAvgModel, groundModel=groundModel)
        self.upstream_only = upstream_only
        self.superpositionModel = superpositionModel

    def calc_blockage_deficit(self, dw_ijlk, **kwargs):
        deficit_ijlk = self.wrap(self.calc_deficit)(dw_ijlk=dw_ijlk, **kwargs)
        if self.upstream_only:
            rotor_pos = -1e-10
            deficit_ijlk *= (dw_ijlk < rotor_pos)
        return deficit_ijlk

    def remove_wake(self, deficit_ijlk, dw_ijlk, cw_ijlk, D_src_il):
        # indices in wake region
        R_ijlk = (D_src_il / 2)[:, na, :, na]
        iw = ((dw_ijlk / R_ijlk >= -self.limiter) & (cabs(cw_ijlk) <= R_ijlk))
        return np.where(iw, 0., deficit_ijlk)


class WakeDeficitModel(DeficitModel, ABC):

    def wake_radius(self, dw_ijlk, **_):
        """Calculates the radius of the wake of the i'th turbine
        for all wind directions(l) and wind speeds(k) at a set of points(j)

        This method must be overridden by subclass

        Arguments required by this method must be added to the class list
        args4deficit

        Returns
        -------
        wake_radius_ijlk : array_like
        """
        raise NotImplementedError("wake_radius not implemented for %s" % self.__class__.__name__)


class ConvectionDeficitModel(WakeDeficitModel):

    @property
    def args4deficit(self):
        args4deficit = WakeDeficitModel.args4deficit.fget(self)
        try:
            if isinstance(self.windFarmModel.superpositionModel, WeightedSum):
                args4deficit |= method_args(self.calc_deficit_convection)
        except AttributeError:
            # A deficit model instantiated and not attached to a wind farm model has no windFarmModel attribute)
            pass
        return args4deficit

    @abstractmethod
    def calc_deficit_convection(self):
        """Calculate wake deficit caused by the x'th most upstream wind turbines
        for all wind directions(l) and wind speeds(k) on a set of points(j)

        This method must be overridden by subclass

        Arguments required by this method must be added to the class list
        args4deficit

        See documentation of EngineeringWindFarmModel for a list of available input arguments

        Returns
        -------
        deficit_centre_ijlk : array_like
            Wind speed deficit caused by the i'th turbine at j'th downstream location, without accounting for crosswind distance (ie cw = 0)
        uc_ijlk : array_like
            Convection velocity of the i'th turbine at locations j
        sigma_sqr_ijlk : array_like
            Squared wake width of i'th turbine at j
        """

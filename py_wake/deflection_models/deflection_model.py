from abc import ABC, abstractmethod
from py_wake.utils.model_utils import method_args


class DeflectionModel(ABC):

    @property
    def args4deflection(self):
        return method_args(self.calc_deflection)

    @abstractmethod
    def calc_deflection(self, dw_ijl, hcw_ijl, dh_ijl, **kwargs):
        """Calculate deflection

        This method must be overridden by subclass

        Arguments required by this method must be added to the class list
        args4deflection

        See documentation of EngineeringWindFarmModel for a list of available input arguments

        Returns
        -------
        dw_ijlk : array_like
            downwind distance from source wind turbine(i) to destination wind turbine/site (j)
            for all wind direction (l) and wind speed (k)
        hcw_ijlk : array_like
            horizontal crosswind distance from source wind turbine(i) to destination wind turbine/site (j)
            for all wind direction (l) and wind speed (k)
        dh_ijlk : array_like
            vertical distance from source wind turbine(i) to destination wind turbine/site (j)
            for all wind direction (l) and wind speed (k)
        """

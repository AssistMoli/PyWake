import inspect
import os
import pkgutil
from py_wake import np
from numpy import newaxis as na
from py_wake.site._site import Site
import warnings


class Model():
    @property
    def args4model(self):
        return method_args(self.__call__)


class DeprecatedModel():
    def __init__(self, new_model):
        warnings.warn(f"""{self.__module__}.{self.__class__.__name__} is deprecated. Use {new_model} instead""",
                      DeprecationWarning, stacklevel=2)


class ModelMethodWrapper():
    def wrap(self, f, wrapper_name='__call__'):
        wrapper = getattr(self, wrapper_name)

        def w(*args, **kwargs):
            return wrapper(f, *args, **kwargs)
        return w


class RotorAvgAndGroundModelContainer():
    def __init__(self, groundModel=None, rotorAvgModel=None):
        self.groundModel = groundModel
        self.rotorAvgModel = rotorAvgModel

    @property
    def args4model(self):
        args4model = set()
        if self.groundModel:
            args4model |= self.groundModel.args4model
        if self.rotorAvgModel:
            args4model |= self.rotorAvgModel.args4model
        return args4model

    @property
    def windFarmModel(self):
        return self._windFarmModel

    @windFarmModel.setter
    def windFarmModel(self, wfm):
        self._windFarmModel = wfm
        if self.groundModel:
            self.groundModel.windFarmModel = wfm
        if self.rotorAvgModel:
            self.rotorAvgModel.windFarmModel = wfm

    def wrap(self, f, wrapper_name='__call__'):
        if self.rotorAvgModel:
            f = self.rotorAvgModel.wrap(f, wrapper_name)
        if self.groundModel:
            f = self.groundModel.wrap(f, wrapper_name)
        return f


def get_exclude_dict():
    from py_wake.deficit_models.deficit_model import ConvectionDeficitModel, WakeDeficitModel,\
        BlockageDeficitModel
    from py_wake.rotor_avg_models.rotor_avg_model import RotorAvgModel, NodeRotorAvgModel
    from py_wake.wind_farm_models.engineering_models import EngineeringWindFarmModel, PropagateDownwind

    from py_wake.superposition_models import LinearSum
    from py_wake.deficit_models.noj import NOJDeficit
    from py_wake.ground_models.ground_models import NoGround
    from py_wake.site.jit_streamline_distance import JITStreamlineDistance
    return {
        "WindFarmModel": ([EngineeringWindFarmModel], [], PropagateDownwind),
        "DeficitModel": ([ConvectionDeficitModel, BlockageDeficitModel, WakeDeficitModel], [RotorAvgModel], NOJDeficit),
        "WakeDeficitModel": ([ConvectionDeficitModel], [RotorAvgModel], NOJDeficit),
        "RotorAvgModel": ([NodeRotorAvgModel], [], None),
        "SuperpositionModel": ([], [], LinearSum),
        "BlockageDeficitModel": ([], [], None),
        "DeflectionModel": ([], [], None),
        "TurbulenceModel": ([], [], None),
        "AddedTurbulenceSuperpositionModel": ([], [], None),
        "GroundModel": ([], [], NoGround),
        "Shear": ([], [], None),
        "StraightDistance": ([], [JITStreamlineDistance], None),

    }


def cls_in(A, cls_lst):
    return str(A) in map(str, cls_lst)


def get_models(base_class):
    if base_class is Site:
        from py_wake.examples.data.iea37._iea37 import IEA37Site
        from py_wake.examples.data.hornsrev1 import Hornsrev1Site
        from py_wake.examples.data.ParqueFicticio._parque_ficticio import ParqueFicticioSite
        return [IEA37Site, Hornsrev1Site, ParqueFicticioSite]
    exclude_cls_lst, exclude_subcls_lst, default = get_exclude_dict()[base_class.__name__]

    model_lst = []
    base_class_module = inspect.getmodule(base_class)
    for loader, module_name, is_pkg in pkgutil.walk_packages([os.path.dirname(base_class_module.__file__)]):
        if 'test' in module_name:
            continue
        module_name = base_class_module.__package__ + '.' + module_name
        import importlib
        try:
            _module = importlib.import_module(module_name)
            for n in dir(_module):
                v = _module.__dict__[n]
                if inspect.isclass(v):
                    if (cls_in(base_class, v.mro()) and
                        not cls_in(v, exclude_cls_lst + [base_class]) and
                        not any([issubclass(v, cls) for cls in exclude_subcls_lst]) and
                            not cls_in(v, model_lst)):
                        model_lst.append(v)
        except ModuleNotFoundError:  # pragma: no cover
            pass

    if default is not None:
        model_lst.remove(model_lst[[m.__name__ for m in model_lst].index(default.__name__)])
    model_lst.insert(0, default)
    return model_lst


# def list_models():
#     for model_type in list(get_exclude_dict().keys()):
#         print("%s (from %s import *)" % (model_type.__name__, ".".join(model_type.__module__.split(".")[:2])))
#         for model in get_models(model_type):
#             if model is not None:
#                 print("\t%s%s" % (model.__name__, str(inspect.signature(model.__init__)).replace('self, ', '')))


def get_signature(cls, kwargs={}, indent_level=0):
    sig = inspect.signature(cls.__init__)

    def get_arg(n, arg_value):
        if arg_value is None:
            arg_value = sig.parameters[n].default
            if 'object at' in str(arg_value):
                arg_value = get_signature(arg_value.__class__, indent_level=(indent_level + 1, 0)[indent_level == 0])
            elif isinstance(arg_value, str):
                arg_value = "'%s'" % arg_value
        else:
            arg_value = get_signature(arg_value, indent_level=(indent_level + 1, 0)[indent_level == 0])
        if arg_value is inspect._empty:
            return n
        if isinstance(arg_value, np.ndarray):
            arg_value = arg_value.tolist()
        return "%s=%s" % (n, arg_value)
    if indent_level:
        join_str = ",\n%s" % (" " * 4 * indent_level)
    else:
        join_str = ", "
    arg_str = join_str.join([get_arg(n, kwargs.get(n, None))
                             for n in sig.parameters if n not in {'self', 'args', 'kwargs'}])
    if indent_level and arg_str:
        return "%s(%s%s)" % (cls.__name__, join_str[1:], arg_str)
    else:
        return "%s(%s)" % (cls.__name__, arg_str)


def get_model_input(wfm, x, y, ws=10, wd=270, yaw=[[[0]]], tilt=[[[0]]]):
    ws, wd = [np.atleast_1d(v) for v in [ws, wd]]
    x, y = map(np.asarray, [x, y])
    wfm.site.distance.setup(src_x_i=[0], src_y_i=[0], src_h_i=[0],
                            dst_xyh_j=(x, y, x * 0))
    dw_ijl, hcw_ijl, dh_ijl = wfm.site.distance(WD_ilk=wd[na, :, na])
    sim_res = wfm([0], [0], ws=ws, wd=wd, yaw=yaw)

    args = {'dw_ijl': dw_ijl, 'hcw_ijl': hcw_ijl, 'dh_ijl': dh_ijl,
            'D_src_il': np.atleast_1d(wfm.windTurbines.diameter())[na]}
    args.update({k: sim_res[n].ilk() for k, n in [('yaw_ilk', 'yaw'),
                                                  ('tilt_ilk', 'tilt'),
                                                  ('WS_ilk', 'WS'),
                                                  ('WS_eff_ilk', 'WS_eff'),
                                                  ('ct_ilk', 'CT')]})
    return args


def check_model(model, cls, arg_name=None, accept_None=True):
    if not isinstance(model, cls):
        if model is None and accept_None:
            return

        if arg_name is not None:
            s = f'Argument, {arg_name}, '
        else:
            s = f'{model} '
        s += f'must be a {cls.__name__} instance'
        if inspect.isclass(model) and issubclass(model, cls):
            raise ValueError(s + f'. Did you forget the brackets: {model.__name__}()')

        raise ValueError(s + f', but is a {model.__class__.__name__} instance')


def fix_shape(arr, shape_or_arr_to_match, allow_number=False, allow_None=False):
    if allow_None and arr is None:
        return arr
    if allow_number and isinstance(arr, (int, float)):
        return arr

    arr = np.asarray(arr)
    if isinstance(shape_or_arr_to_match, tuple):
        shape = shape_or_arr_to_match
    else:
        shape = np.asarray(shape_or_arr_to_match).shape
    return np.broadcast_to(arr.reshape(arr.shape + (1,) * (len(shape) - len(arr.shape))), shape)


def method_args(method):
    return set(inspect.getfullargspec(method).args) - {'self', 'func'}


def main():
    if __name__ == '__main__':
        from py_wake.superposition_models import SuperpositionModel
        print(get_models(SuperpositionModel))
        for c in get_models(SuperpositionModel):
            print(isinstance(c(), SuperpositionModel), c)


main()

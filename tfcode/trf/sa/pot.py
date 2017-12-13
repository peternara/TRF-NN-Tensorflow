import tensorflow as tf
import os

from base import *
from lm import *
from trf.common import feat
from trf.sa import net


class BaseConfig(wb.Config):
    def __init__(self, type_name):
        wb.Config.value_encoding_map[lr.LearningRate] = str

        self.type = type_name

    def __str__(self):
        return 'NonePotential'


class FeatConfig(BaseConfig):
    def __init__(self, data):
        super().__init__('feat')

        self.feat_type_file = None
        self.feat_cluster = None
        self.var_gap = 1e-3

    def __str__(self):
        feat_name = os.path.split(self.feat_type_file)[-1]
        feat_name = os.path.splitext(feat_name)[0]
        return 'feat{}'.format(feat_name)


class NetConfig(BaseConfig, net.Config):
    def __init__(self, data):
        BaseConfig.__init__(self, 'net')
        net.Config.__init__(self, data)

    def __str__(self):
        return net.Config.__str__(self)


class Base(object):
    def get_param_num(self):
        return 0

    def get_value(self, seq_list):
        return np.zeros(len(seq_list))

    def initialize(self):
        pass

    def update(self, data_list, data_scalars, sample_list, sample_scalars, learning_rate=1.0):
        pass

    def save(self, fname):
        pass

    def restore(self, fname):
        pass

    @property
    def global_step(self):
        return None


class FeatPhi(Base):
    def __init__(self, config, data, opt_method):
        self.config = config
        self.data = data
        self.opt_method = opt_method

        self.len_factor = self.config.pi_true / self.config.pi_0

        wftype, cftype = feat.separate_type(feat.read_feattype_file(self.config.feat_type_file))
        self.wfeat = feat.Feats(wftype)
        if self.config.feat_cluster is not None:
            self.cfeat = feat.Feats(cftype)
        else:
            self.cfeat = None

        self.update_op = None

    def get_param_num(self):
        n = self.wfeat.num
        if self.cfeat is None:
            return n

        return n + self.cfeat.num

    def get_value(self, seq_list):
        w1 = self.wfeat.seq_list_weight(seq_list)
        if self.cfeat is None:
            return w1

        w2 = self.wfeat.seq_list_weight(self.data.seqs_to_class(seq_list))
        return np.array(w1) + np.array(w2)

    def feat_count(self, cur_feat, seq_list, seq_scalar):
        buf = np.zeros_like(cur_feat.values)
        for seq, d in zip(seq_list, seq_scalar):
            for i in cur_feat.seq_find(seq):
                buf[i] += d
        return buf

    def get_gradient(self, data_list, data_scalar, sample_list, sample_scalar):

        # data_scalar = np.ones(len(data_list)) / len(data_list)
        # sample_len = np.array([len(x) for x in sample_list])
        # sample_scalar = self.len_factor[sample_len - self.config.min_len] / len(sample_list)

        exp_d = self.feat_count(self.wfeat, data_list, data_scalar)
        exp_s = self.feat_count(self.wfeat, sample_list, sample_scalar)

        if self.cfeat is None:
            return exp_d - exp_s

        exp_d2 = self.feat_count(self.cfeat, data_list, data_scalar)
        exp_s2 = self.feat_count(self.cfeat, sample_list, sample_scalar)
        return np.concatenate([exp_d - exp_s, exp_d2 - exp_s2])

    def update(self, data_list, data_scalars, sample_list, sample_scalars, learning_rate=1.0):
        g = self.get_gradient(data_list, data_scalars, sample_list, sample_scalars)
        d = self.update_op.update(-g, learning_rate)

        self.wfeat.values += d[0: self.wfeat.num]
        if self.cfeat is not None:
            self.cfeat.values += d[self.wfeat.num:]

    def initialize(self):
        print('[{}.{}] load features ...'.format(__name__, self.__class__.__name__))
        self.wfeat.load_from_seqs(self.data.datas[0])
        if self.cfeat is not None:
            self.cfeat.load_from_seqs(self.data.seqs_to_class(self.data.datas[0]))
        self.update_op = wb.ArrayUpdate(self.get_param_num(), {'name': self.opt_method})

    def save(self, fname):
        with open(fname + '.feat', 'wt') as f:
            self.wfeat.save(f)
            if self.cfeat is not None:
                self.cfeat.save(f)

    def restore(self, fname):
        with open(fname + '.feat', 'rt') as f:
            self.wfeat.restore(f)
            if self.cfeat is not None:
                self.cfeat.restore(f)


class NetPhi(Base):
    def __init__(self, config, data, opt_method='sgd', device='/gpu:0'):
        self.config = config
        self.data = data

        # revise the opt_method
        config.opt_method = opt_method

        self.train_net = net.NetBase(config, is_training=True, device=device, name='trfnet', reuse=None)
        self.eval_net = net.NetBase(config, is_training=False, device=device, name='trfnet', reuse=True)

        self.saver = tf.train.Saver(self.train_net.vars)

    def get_param_num(self):
        return self.train_net.get_param_num()

    def get_value(self, seq_list):
        return self.eval_net.get_phi(seq_list)

    def get_value_for_train(self, seq_list):
        return self.train_net.get_phi(seq_list)

    def initialize(self):
        pass

    def update(self, data_list, data_scalars, sample_list, sample_scalars, learning_rate=1.0):
        self.train_net.update(data_list, data_scalars, sample_list, sample_scalars, learning_rate=learning_rate)

    def save(self, fname):
        self.saver.save(tf.get_default_session(), fname + '.ckpt')

    def restore(self, fname):
        self.saver.restore(tf.get_default_session(), fname + '.ckpt')


class NormBase(object):
    def get_logz(self, lengths=None):
        pass

    def set_logz1(self, logz1):
        pass

    def update(self, seq_list, learning_rate=1.0):
        pass

    def save(self, fname):
        pass

    def restore(self, fname):
        pass


class NormFixed(NormBase):
    def __init__(self, config, data, opt_method='sgd'):
        self.config = config
        self.data = data
        self.opt_method = opt_method
        self.logz1 = self.config.init_logz[0]

    def get_logz(self, lengths=None):
        if lengths is None:
            lengths = np.linspace(self.config.min_len, self.config.max_len,
                                  self.config.max_len - self.config.min_len + 1)
        return self.logz1 * (lengths - self.config.min_len + 1)

    def set_logz1(self, logz1):
        self.logz1 = logz1

    def update(self, seq_list, learning_rate=1.0):
        pass

    def save(self, fname):
        with open(fname, 'wt') as f:
            f.write('logz1={}\n'.format(self.logz1))

    def restore(self, fname):
        with open(fname, 'rt') as f:
            self.logz1 = float(f.readline().split('=')[-1])


class Norm(NormBase):
    def __init__(self, config, data, opt_method='sgd'):
        self.config = config
        self.data = data
        self.opt_method = opt_method

        self.zeta = np.array(self.config.init_logz) - self.config.init_logz[0]
        self.logz1 = self.config.init_logz[0]
        self.update_op = wb.ArrayUpdate(self.zeta, {'name': self.opt_method})

    def get_logz(self, lengths=None):
        if lengths is None:
            return self.zeta + self.logz1
        return self.zeta[np.array(lengths) - self.config.min_len] + self.logz1

    def set_logz1(self, logz1):
        self.logz1 = logz1

    def set_logz(self, logz):
        """logz[config.min_len: config.max_len+1]"""
        self.logz1 = logz[0]
        self.zeta = logz - logz[0]

    def get_gradient(self, sample_list):
        grad = np.zeros_like(self.zeta)
        for x in sample_list:
            grad[len(x) - self.config.min_len] += 1
        grad /= len(sample_list)
        grad /= self.config.pi_0[self.config.min_len:]
        grad = np.minimum(grad, 1.0)
        return grad

    def update(self, seq_list, learning_rate=1.0):
        g = self.get_gradient(seq_list)

        self.zeta += self.update_op.update(-g, learning_rate)
        self.zeta -= self.zeta[0]

    def save(self, fname):
        with open(fname, 'wt') as f:
            f.write('logz1={}\n'.format(self.logz1))
            f.write('len\tzeta\n')
            for i, v in enumerate(self.zeta):
                f.write('{}\t{}\n'.format(i + self.config.min_len, v))

    def restore(self, fname):
        with open(fname, 'rt') as f:
            self.logz1 = float(f.readline().split('=')[-1])
            f.readline()
            lens = []
            zeta = []
            for line in f:
                a = line.split()
                lens.append(int(a[0]))
                zeta.append(float(a[1]))
            self.zeta = np.array(zeta)
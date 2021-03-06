import tensorflow as tf
import os
import sys
import numpy as np

from base import *
from lm import *
from trf.sa import *
# from trf import trfjsa


def create_name(config):
    return str(config)


def main(_):
    data = reader.Data().load_raw_data(reader.word_raw_dir(),
                                       add_beg_token='</s>', add_end_token='</s>',
                                       add_unknwon_token=None,
                                       max_length=None)
    # lstm config
    config = trf.Config(data)

    config.chain_num = 100
    config.multiple_trial = 10
    # config.auxiliary_model = 'lstm'
    config.auxiliary_config.embedding_size = 32
    config.auxiliary_config.hidden_size = 32
    config.auxiliary_config.hidden_layers = 1
    config.auxiliary_config.batch_size = 100
    config.auxiliary_config.step_size = 10
    config.auxiliary_config.learning_rate = 1.0

    config.feat_config.feat_type_file = '../../tfcode/feat/g4.fs'

    config.lr_feat = lr.LearningRateEpochDelay(1e-3)
    config.lr_net = lr.LearningRateEpochDelay(1e-3)
    config.lr_logz = lr.LearningRateEpochDelay(0.1)
    config.opt_feat_method = 'adam'
    config.opt_net_method = 'adam'
    config.opt_logz_method = 'sgd'

    name = create_name(config)
    logdir = wb.mkdir('trf_sa/' + name, is_recreate=True)
    sys.stdout = wb.std_log(os.path.join(logdir, 'trf.log'))
    print(logdir)
    config.print()

    data.write_vocab(logdir + '/vocab.txt')
    data.write_data(data.datas[0], logdir + '/train.id')
    data.write_data(data.datas[1], logdir + '/valid.id')
    data.write_data(data.datas[2], logdir + '/test.id')

    # wb.rmdir(logdirs)
    with tf.Graph().as_default():
        m = trf.TRF(config, data, logdir=logdir, device='/gpu:0')

        sv = tf.train.Supervisor(logdir=os.path.join(logdir, 'logs'),
                                 global_step=m.global_step)
        sv.summary_writer.add_graph(tf.get_default_graph())  # write the graph to logs
        session_config = tf.ConfigProto(allow_soft_placement=True, log_device_placement=False)
        session_config.gpu_options.allow_growth = True
        with sv.managed_session(config=session_config) as session:

            with session.as_default():

                # print(m.true_logz())
                #
                # m.test_sample()

                m.train(operation=trf.DefaultOps(m, reader.word_nbest()))

if __name__ == '__main__':
    # test_net()
    tf.app.run(main=main)

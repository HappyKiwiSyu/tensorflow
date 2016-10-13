# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time

import numpy as np
import tensorflow as tf

# from functools import reduce


class ConditionalAccumulatorTest(tf.test.TestCase):

  def testConstructor(self):
    with tf.Graph().as_default():
      q = tf.ConditionalAccumulator(tf.float32, name="Q")
    self.assertTrue(isinstance(q.accumulator_ref, tf.Tensor))
    self.assertEquals(tf.string_ref, q.accumulator_ref.dtype)
    self.assertProtoEquals("""
      name:'Q' op:'ConditionalAccumulator'
      attr { key: 'dtype' value { type: DT_FLOAT } }
      attr { key: 'shape' value { shape { unknown_rank: true} } }
      attr { key: 'container' value { s: '' } }
      attr { key: 'shared_name' value { s: '' } }
      """, q.accumulator_ref.op.node_def)

  def testConstructorWithShape(self):
    with tf.Graph().as_default():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1, 5, 2, 8]))
    self.assertTrue(isinstance(q.accumulator_ref, tf.Tensor))
    self.assertEquals(tf.string_ref, q.accumulator_ref.dtype)
    self.assertProtoEquals("""
      name:'Q' op:'ConditionalAccumulator'
      attr { key: 'dtype' value { type: DT_FLOAT } }
      attr { key: 'shape' value { shape { dim {size: 1 }
                                          dim {size: 5 }
                                          dim {size: 2 }
                                          dim {size: 8 }
      } } }
      attr { key: 'container' value { s: '' } }
      attr { key: 'shared_name' value { s: '' } }
      """, q.accumulator_ref.op.node_def)

  def testAccumulatorSizeEmpty(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(tf.float32, name="Q")
      self.assertEqual(q.num_accumulated().eval(), 0)

  def testAccumulatorSetGlobalStep(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      set_global_step_op = q.set_global_step(1)
      set_global_step_op.run()

  def testAccumulatorApplyGradFloat32(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      accum_op = q.apply_grad((10.0,))
      accum_op.run()

  def testDtypes(self):
    with self.test_session() as sess:
      dtypes = [tf.float16, tf.float32, tf.float64]

      for i in range(len(dtypes)):
        dtype = dtypes[i]
        q = tf.ConditionalAccumulator(dtype, shape=tf.TensorShape([1]))

        elems = np.arange(10).astype(dtype.as_numpy_dtype)
        for e in elems:
          q.apply_grad((e,)).run()

        result = sess.run(q.take_grad(1))

        self.assertEqual(sum(elems) / len(elems), result)

  def testAccumulatorMultipleAccumulators(self):
    with self.test_session():
      q_f32_0 = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      q_f32_1 = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      q_f16_0 = tf.ConditionalAccumulator(
          tf.float16, name="Q", shape=tf.TensorShape([1]))
      q_f16_1 = tf.ConditionalAccumulator(
          tf.float16, name="Q", shape=tf.TensorShape([1]))

      accums = [q_f16_0, q_f16_1, q_f32_0, q_f32_1]
      for i in range(len(accums)):
        accums[i].apply_grad((i + 10.0,)).run()

      for i in range(len(accums)):
        result = accums[i].take_grad(1).eval()
        self.assertEqual(result, i + 10.0)

  def testAccumulatorApplyAndTakeGradWithShape(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(tf.float32, name="Q", shape=(3, 2))
      elems = [[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
               [[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]]]
      elems_ave = [[(a + b) / len(elems) for a, b in zip(x, y)]
                   for x, y in zip(elems[0], elems[1])]
      accum_ops = [q.apply_grad(x) for x in elems]
      takeg_t = q.take_grad(1)

      for accum_op in accum_ops:
        accum_op.run()

      is_all_equal = True
      val = takeg_t.eval()
      for i in range(len(val)):
        for j in range(len(val[i])):
          is_all_equal &= (val[i][j] == elems_ave[i][j])
      self.assertTrue(is_all_equal)

  def testAccumulatorApplyGradWithWrongShape(self):
    q = tf.ConditionalAccumulator(tf.float32, name="Q", shape=(3, 2))

    with self.assertRaises(ValueError):
      q.apply_grad([[1.0, 2.0], [3.0, 4.0]])

    with self.assertRaises(ValueError):
      q.apply_grad([[1.0], [2.0], [3.0]])

  def testAccumulatorDynamicShape(self):
    with self.test_session() as sess:
      q = tf.ConditionalAccumulator(tf.float32, name="Q", shape=None)

      x = tf.placeholder(tf.float32)

      accum_op = q.apply_grad(x)

      elems = [[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
               [[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]]]
      elems_ave = [[(a + b) / len(elems) for a, b in zip(c, d)]
                   for c, d in zip(elems[0], elems[1])]
      takeg_t = q.take_grad(1)

      for elem in elems:
        sess.run(accum_op, feed_dict={x: elem})

      is_all_equal = True
      val = takeg_t.eval()
      for i in range(len(val)):
        for j in range(len(val[i])):
          is_all_equal &= (val[i][j] == elems_ave[i][j])
      self.assertTrue(is_all_equal)

  def testAccumulatorWrongDynamicShape(self):
    with self.test_session() as sess:
      q = tf.ConditionalAccumulator(tf.float32, name="Q", shape=None)

      x = tf.placeholder(tf.float32)

      accum_op = q.apply_grad(x)

      # First successful apply_grad determines shape
      sess.run(accum_op, feed_dict={x: [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]})

      with self.assertRaises(tf.errors.InvalidArgumentError):
        sess.run(accum_op, feed_dict={x: [[1.0, 2.0], [3.0, 4.0]]})

      with self.assertRaises(tf.errors.InvalidArgumentError):
        sess.run(accum_op, feed_dict={x: [[1.0], [2.0], [3.0]]})

  def testAccumulatorSizeAfterApplyGrad(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      accum_op = q.apply_grad((10.0,))
      self.assertEqual(q.num_accumulated().eval(), 0)
      accum_op.run()
      self.assertEqual(q.num_accumulated().eval(), 1)
      accum_op.run()
      self.assertEqual(q.num_accumulated().eval(), 2)

  def testAccumulatorSizeAfterApplyGradAndTakeGrad(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      accum_op = q.apply_grad((10.0,))
      extract_t = q.take_grad(2)

      # Applying gradient multiple times to increase size from 0 to 2.
      self.assertEqual(q.num_accumulated().eval(), 0)
      accum_op.run()
      self.assertEqual(q.num_accumulated().eval(), 1)
      accum_op.run()
      self.assertEqual(q.num_accumulated().eval(), 2)

      # Extract will reduce size to 0
      extract_t.op.run()
      self.assertEqual(q.num_accumulated().eval(), 0)

      # Take gradients always sets the size back to 0 if successful.
      accum_op = q.apply_grad((10.0,), local_step=1)
      accum_op.run()
      accum_op.run()
      accum_op.run()
      accum_op.run()
      self.assertEqual(q.num_accumulated().eval(), 4)
      extract_t.op.run()
      self.assertEqual(q.num_accumulated().eval(), 0)

  def testAccumulatorTakeGrad(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      elems = [10.0, 20.0]
      elems_ave = sum(elems) / len(elems)

      accum_ops = [q.apply_grad((x,), local_step=0) for x in elems]
      takeg_t = q.take_grad(1)

      for accum_op in accum_ops:
        accum_op.run()

      val = takeg_t.eval()
      self.assertEqual(elems_ave, val)

      accum_ops = [q.apply_grad((x,), local_step=1) for x in elems]
      takeg_t = q.take_grad(tf.constant(1))

      for accum_op in accum_ops:
        accum_op.run()

      val = takeg_t.eval()
      self.assertEqual(elems_ave, val)

  def testAccumulatorInvalidTakeGrad(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      elems = [10.0, 20.0]
      accum_ops = [q.apply_grad((x,)) for x in elems]

      takeg_t = q.take_grad(-1)

      for accum_op in accum_ops:
        accum_op.run()

      with self.assertRaises(tf.errors.InvalidArgumentError):
        takeg_t.eval()

  def testAccumulatorRepeatedTakeGrad(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))

      elems = [10.0, 20.0]
      elems_ave = sum(elems) / len(elems)
      accum_ops = [q.apply_grad((x,), local_step=0) for x in elems]
      takeg_t = q.take_grad(1)

      for accum_op in accum_ops:
        accum_op.run()

      val = takeg_t.eval()
      self.assertEqual(elems_ave, val)

      elems = [20.0, 30.0]
      elems_ave = sum(elems) / len(elems)
      accum_ops = [q.apply_grad((x,), local_step=1) for x in elems]
      takeg_t = q.take_grad(1)

      for accum_op in accum_ops:
        accum_op.run()

      val = takeg_t.eval()
      self.assertEqual(elems_ave + 0.0, val)

  def testAccumulatorIncrementGlobalStep(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))

      global_step = tf.Variable(0, name="global_step")
      new_global_step = tf.add(global_step, 1)
      inc_global_step = tf.assign(global_step, new_global_step)

      set_global_step_op = q.set_global_step(new_global_step)

      tf.initialize_all_variables().run()
      for _ in range(3):
        set_global_step_op.run()
        inc_global_step.eval()

  def testAccumulatorSetGlobalStepPreventsAccumulation(self):
    with self.test_session():
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))

      local_steps = range(1000, 1005)
      accum_ops = [q.apply_grad((0.0 + x,), local_step=x) for x in local_steps]

      for ls in local_steps:
        set_global_step_op = q.set_global_step(ls)
        set_global_step_op.run()

        for accum_op in accum_ops:
          accum_op.run()
        takeg_t = q.take_grad(1)

        val = takeg_t.eval()
        self.assertEqual(0.0 + sum(x for x in local_steps
                                   if x >= ls) / sum(1 for x in local_steps
                                                     if x >= ls), val)

  def testParallelApplyGrad(self):
    with self.test_session() as sess:
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      elems = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
      accum_ops = [q.apply_grad((x,), local_step=0) for x in elems]
      takeg_t = q.take_grad(1)

      def apply_grad(accum_op):
        sess.run(accum_op)

      threads = [self.checkedThread(
          target=apply_grad, args=(o,)) for o in accum_ops]

      for thread in threads:
        thread.start()
      for thread in threads:
        thread.join()

      val = takeg_t.eval()

      self.assertEqual(val, sum(elems) / len(elems))

  def testParallelTakeGrad(self):
    with self.test_session() as sess:
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      elems = [e for e in range(10)]
      accum_ops = [q.apply_grad((np.float32(e),), local_step=e) for e in elems]
      takeg_t = q.take_grad(1)

      def apply_grad():
        for accum_op in accum_ops:
          time.sleep(1.0)
          sess.run(accum_op)

      apply_grad_thread = self.checkedThread(target=apply_grad)

      results = []

      def take_grad():
        results.append(sess.run(takeg_t))

      threads = [self.checkedThread(target=take_grad) for _ in range(10)]

      for thread in threads:
        thread.start()
      apply_grad_thread.start()

      for thread in threads:
        thread.join()
      apply_grad_thread.join()

      self.assertItemsEqual(elems, results)

  def testAccumulatorApplyAndBlockingTake(self):
    with self.test_session() as sess:
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))

      elems = [10.0, 20.0, 30.0]
      elems_ave = sum(elems) / len(elems)
      accum_ops = [q.apply_grad((x,), local_step=0) for x in elems]
      takeg_t = q.take_grad(3)

      def apply_grad():
        time.sleep(1.0)
        for accum_op in accum_ops:
          sess.run(accum_op)

      return_array = []

      def take_grad():
        return_array.append(sess.run(takeg_t))

      accum_thread = self.checkedThread(target=apply_grad)
      takeg_thread = self.checkedThread(target=take_grad)
      accum_thread.start()
      takeg_thread.start()
      accum_thread.join()
      takeg_thread.join()

      self.assertEqual([elems_ave], return_array)

  def _blocking_takeg(self, sess, takeg_op):
    with self.assertRaisesOpError("TakeGrad operation was cancelled"):
      sess.run(takeg_op)

  def testAccumulatorCancel(self):
    with self.test_session() as sess:
      q = tf.ConditionalAccumulator(
          tf.float32, name="Q", shape=tf.TensorShape([1]))
      takeg_t = q.take_grad(1)

      takeg_thread = self.checkedThread(
          self._blocking_takeg, args=(sess, takeg_t))

      takeg_thread.start()

      time.sleep(1.0)

      sess.close()  # Will cancel blocked operation

      takeg_thread.join()

if __name__ == "__main__":
  tf.test.main()

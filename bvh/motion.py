# -*- coding: utf-8 -*-

import bvh_parser as bp
from coordinate_transform import *

try:
    from graphviz import Digraph
except:
    print("Can't import graphviz. graphviz is not existance")
from collections import defaultdict
from pprint import pprint
import pandas as pd
import pickle
import os

from motion_variables import MotionVariables

class Motion(object):
    def __init__(self, file_dir, filename, devise="optitrack", re_load=False, bone_names=None):
        self.file_dir = file_dir
        self.filename = filename
        self.devise = devise
        self.bone_names = bone_names

        ext = filename.split('.')
        ext = ext[len(ext)-1]
        if ext == 'bvh':
            self.motion = bp.bvh(file_dir+filename)
            self.data_size = len(self.motion.data)
            self.motion_variables = MotionVariables(self.devise)

        self.extract_joint_names()
        self.get_joint_hierarchy_tree()

        savepath = self.file_dir+self.filename.split('.')[0]+".pkl"
        if (not os.path.exists(savepath)) or re_load == True:
            print("First analysis start!!!")
            
            self.create_joint_info_frame()
            with open(savepath, mode='wb') as f:
                pickle.dump(self.joint_info_dataframe, f, protocol=2)
        else:
            print("Loading analyzed data ...")
            with open(savepath, mode='rb') as f:
                self.joint_info_dataframe = pickle.load(f)

    def get_joint_info(self, frame):
        self.joint_info_mat = defaultdict(list)
        self.joint_info = defaultdict(list)
        self.get_joint_info_matrix(self.joint_hierarchy_tree, frame)
        self.pos_dict = {}
        self.angle_dict = {}
        self.axis_dict = {}
        self.extract_joint_info()

    def extract_joint_info(self):
        for joint in self.joint_info:
            mat = dict(self.joint_info)[joint][0]
            if not self.bone_names is None:
                if joint in self.bone_names:
                    tmp, self.angle_dict[joint] = get_rotation_info(get_rotation_matrix(mat))
                    self.pos_dict[joint] = get_position_info(mat)

                    comp_axis = np.array([0., 0., 1.])
                    axis_change_judge = np.dot(tmp, comp_axis)
                    if axis_change_judge < 0.:
                        self.axis_dict[joint] = -tmp
                    else:
                        self.axis_dict[joint] = tmp

            else:
                tmp, self.angle_dict[joint] = get_rotation_info(get_rotation_matrix(mat))
                self.pos_dict[joint] = get_position_info(mat)

                comp_axis = np.array([0., 0., 1.])
                axis_change_judge = np.dot(tmp, comp_axis)
                if axis_change_judge < 0.:
                    self.axis_dict[joint] = -tmp
                else:
                    self.axis_dict[joint] = tmp

    def get_joint_info_matrix(self, joint_tree, frame):
        for target in joint_tree:
            # print('target',target)
            self.joint_hierarchy = self.get_joint_hierarchy(target)
            # pprint(self.joint_hierarchy)

            # 処理のコード
            # Check order list have 'Rotation' information
            order = self.get_channels(target)
            rotation_check = len([l for l in order if 'rotation' in l])
            # print(order, rotation_check)

            # Initialize transformation matrix
            rotation_mat_tmp = np.identity(3)
            mat = np.identity(4)

            # Get rotation order information for target joint
            rotation_order = []
            for channel in order:
                if 'rotation' in channel:
                    rotation_order.append(target+'-'+channel)
            # print(rotation_order)

            # Prepare simultaneous transformation matrix for target joint
            if any(('rotation' in x for x in order)) == True:
                for tmp in rotation_order:
                    rotation_mat_tmp = np.dot(rotation_mat_tmp, get_rotation(tmp[len(tmp)-9],deg2rad(self.motion.data[tmp].values[frame])))

            if self.motion_variables.devise == "optitrack" and target == self.motion_variables.MOTIVE_BONE_NAMES[0]:
                offsets = self.get_offsets_from_root_pos()
            else:
                offsets = self.get_offsets(target)
            mat_tmp = get_simultaneous_matrix(rotation_mat_tmp,offsets)

            self.joint_info_mat[target].append([mat_tmp])

            for joint in self.joint_hierarchy:
                mat = np.dot(mat, dict(self.joint_info_mat)[joint][0][0])
            self.joint_info[target].append(mat)

            self.get_joint_info_matrix(joint_tree[target],frame)

    def create_joint_info_frame(self):
        degree_lists = {}
        rotation_axis_vec_lists = {}
        position_lists = {}
        
        print("Analyzing motion data ..", end="", flush=True)
        for joint in self.get_joint_names():
            if not self.bone_names is None:
                if joint in self.bone_names:
                    degree_lists[joint] = []
                    rotation_axis_vec_lists[joint] = []
                    position_lists[joint] = []
            else:
                degree_lists[joint] = []
                rotation_axis_vec_lists[joint] = []
                position_lists[joint] = []

        for i in range(self.data_size):
            if i%100 == 0:
                print("..", end="", flush=True)
            self.get_joint_info(i)
            for joint in self.get_joint_names():
                if not self.bone_names is None:
                    if joint in self.bone_names:
                        degree_lists[joint].append(self.angle_dict[joint])
                        rotation_axis_vec_lists[joint].append(self.axis_dict[joint])
                        position_lists[joint].append(self.pos_dict[joint])
                else:
                    degree_lists[joint].append(self.angle_dict[joint])
                    rotation_axis_vec_lists[joint].append(self.axis_dict[joint])
                    position_lists[joint].append(self.pos_dict[joint])

        print("")

        tmp_dict = {}
        for joint in self.get_joint_names():
            if not self.bone_names is None:
                if joint in self.bone_names:
                    tmp_dict[joint+'-rotation'] = degree_lists[joint]
                    tmp_dict[joint+'-axis'] = rotation_axis_vec_lists[joint]
                    tmp_dict[joint+'-position'] = position_lists[joint]
            else:
                tmp_dict[joint+'-rotation'] = degree_lists[joint]
                tmp_dict[joint+'-axis'] = rotation_axis_vec_lists[joint]
                tmp_dict[joint+'-position'] = position_lists[joint]
        self.joint_info_dataframe = pd.DataFrame.from_dict(tmp_dict)
        self.joint_info_dataframe['time'] = self.get_time()
        print("analysis ended!!!")

    def get_joint_hierarchy_tree(self):
        self.joint_hierarchy_tree = self.tree()
        added_pair = []
        for joint in self.get_joint_names():
            hierarchy = self.get_joint_hierarchy(joint)
            self.add(self.joint_hierarchy_tree, hierarchy)
        self.joint_hierarchy_tree = self.dicts(self.joint_hierarchy_tree)
        # pprint(self.joint_hierarchy_tree)

    def tree(self):
        return defaultdict(self.tree)

    def add(self, t, keys):
        for key in keys:
            t = t[key]

    def dicts(self, t):
        return {k: self.dicts(t[k]) for k in t}

    def print_dict_keys(self, t):
        for key in t:
            if t[key] == {}:
                print(key,t[key])
            self.print_dict_keys(t[key])

    def get_joint_hierarchy(self,joint):
        joint_hierarchy = [joint]
        # print('target joint : ',joint)
        parent_joint = joint
        while not parent_joint == None:
            parent_joint = self.motion.skeleton[parent_joint]['parent']
            joint_hierarchy.insert(0,parent_joint)
            # print('parent joint : ',parent_joint)
        return joint_hierarchy[1:len(joint_hierarchy)]

    def export_joint_hierarchy(self,export_name='joint_hierarchy'):
        # formatはpngを指定(他にはPDF, PNG, SVGなどが指定可)
        G = Digraph(format='png') #　有向グラフ初期化
        G.attr('node', shape='circle') # ノードの形

        added_pair = []
        # ノードの追加
        for joint in self.get_joint_names():
            G.node(joint, joint) # ノード作成
        # 辺の追加
        for joint in self.get_joint_names():
            hierarchy = self.get_joint_hierarchy(joint)
            for i in range(len(hierarchy)-1):
                if any((x == [hierarchy[i],hierarchy[i+1]] for x in added_pair)) == False:
                    G.edge(hierarchy[i],hierarchy[i+1])
                    added_pair.append([hierarchy[i],hierarchy[i+1]])
        G.render(export_name)

    def get_parent(self, child_joint):
        return self.get_joint_hierarchy(child_joint)[len(self.get_joint_hierarchy(child_joint))-2]

    def get_child(self, parent_joint):
        parent_index = self.joint_hierarchy.index(parent_joint)
        print(self.joint_hierarchy,'parent index', parent_index)
        if not parent_index == len(self.joint_hierarchy)-1:
            child = self.joint_hierarchy[parent_index+1]
            return child
        else:
            return None

    def get_offsets(self, joint):
        return self.motion.skeleton[joint]['offsets']

    def get_axis(self, joint, frame):
        if joint+'-axis' in self.joint_info_dataframe:
            return self.joint_info_dataframe[joint+'-axis'].values[frame]
        return None

    def get_angle(self, joint, frame):
        if joint+'-rotation' in self.joint_info_dataframe:
            return self.joint_info_dataframe[joint+'-rotation'].values[frame]
        return None

    def get_position(self, joint, frame, scale):
        if joint+'-position' in self.joint_info_dataframe:
            return self.joint_info_dataframe[joint+'-position'].values[frame]*scale
        return None

    def get_joint_position(self, joint, scale):
        if joint in self.pos_dict:
            return self.pos_dict[joint]*scale
        return None

    def extract_joint_names(self):
        self.joint_names = []
        for joint in self.motion.skeleton:
            self.joint_names.append(joint)
        return self.joint_names

    def get_joint_names(self):
        return self.joint_names

    def get_channels(self,joint):
        return self.motion.skeleton[joint]['channels']

    def get_time(self):
        return self.motion.data['time'].values

    def save_to_csv(self, savename='tmp.csv'):
        self.joint_info_dataframe.to_csv(savename)

    def save_angle_data_to_csv(self, savename="tmp.csv"):
        angle_df = self.joint_info_dataframe.copy()
        for joint in self.get_joint_names():
            if not self.bone_names is None:
                if joint in self.bone_names:
                    del angle_df[joint+'-axis']
                    del angle_df[joint+'-position']
            else:
                del angle_df[joint+'-axis']
                del angle_df[joint+'-position']

        angle_df.to_csv(savename)

    def save_axis_data_to_csv(self, savename="tmp.csv"):
        axis_df = self.joint_info_dataframe.copy()
        for joint in self.get_joint_names():
            if not self.bone_names is None:
                if joint in self.bone_names:
                    del axis_df[joint+'-rotation']
                    del axis_df[joint+'-position']
            else:
                del axis_df[joint+'-rotation']
                del axis_df[joint+'-position']

        axis_df.to_csv(savename)

    def save_position_data_to_csv(self, savename="tmp.csv"):
        pos_df = self.joint_info_dataframe.copy()
        for joint in self.get_joint_names():
            if not self.bone_names is None:
                if joint in self.bone_names:
                    del pos_df[joint+'-axis']
                    del pos_df[joint+'-rotation']
            else:
                del pos_df[joint+'-axis']
                del pos_df[joint+'-rotation']
        pos_df.to_csv(savename)
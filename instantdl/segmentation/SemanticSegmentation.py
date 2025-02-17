'''
InstantDL
Written by Dominik Waibel and Ali Boushehri

In this file the functions are started to train and test the networks
'''

from instantdl.utils import *
from instantdl.segmentation.UNet_models import UNetBuilder
from instantdl.data_generator.metrics4losses import *
import random
random.seed(1)
tf.reset_default_graph()
tf.random.set_random_seed(1)
np.random.seed(1)

class SemanticSegmentation(object):
    def __init__(   self,
                    use_algorithm,
                    path,
                    pretrained_weights = None,
                    batchsize = 2,
                    iterations_over_dataset = 100,
                    data_gen_args = None,
                    loss_function = "mse",
                    num_classes = 1,
                    image_size = None,
                    seeds=False,
                    calculate_uncertainty = False,
                    evaluation = True):

        self.use_algorithm = "SemanticSegmentation"
        self.path = path
        self.pretrained_weights = pretrained_weights
        self.batchsize = batchsize
        self.iterations_over_dataset = iterations_over_dataset
        self.loss_function = loss_function
        self.num_classes = num_classes
        self.image_size = image_size
        self.calculate_uncertainty = calculate_uncertainty
        self.evaluation = evaluation
        if data_gen_args is None:
            self.data_gen_args = dict()
        else:
            self.data_gen_args = data_gen_args
    
    def data_prepration(self): 
        '''
        Get the number of input images and their shape
        If the last image dimension,. which should contain the channel information (1 or 3) is not existing e.g. for 
        (512,512) add a 1 as the channel number.
        '''
        if self.image_size == False or self.image_size == None:
            Training_Input_shape, num_channels, Input_image_shape = get_input_image_sizes(self.path, self.use_algorithm)
        else:
            Training_Input_shape = self.image_size
            num_channels = int(self.image_size[-1])
            data_path = self.path + '/train'
            img_file = os.listdir(data_path + "/image/")[0]
            Input_image_shape = np.array(np.shape(np.array(import_image(data_path + "/image/" + img_file))))

        ''' 
        Check if the 2D or 3D Pipeline is needed
        '''
        if len(Training_Input_shape[:-1]) == 3:
            data_dimensions = 3
        if len(Training_Input_shape[:-1]) == 2:
            data_dimensions = 2

        logging.info("Image dimensions are: %s D" % data_dimensions )

        Folders = ["image", "image1", "image2", "image3", "image4", "image5", "image6", "image7"]
        number_input_images = len([element for element in os.listdir(self.path + "/train/") if element in Folders])
        network_input_size = np.array(Training_Input_shape)
        network_input_size[-1] = int(Training_Input_shape[-1]) * number_input_images
        network_input_size = tuple(network_input_size)
        logging.info("Number of input folders is: %s" % number_input_images)
        logging.info("UNet input shape %s" % (network_input_size,))

        '''
        Import filenames and split them into train and validation set according to 
        the variable -validation_split = 20%
        '''
        data_path = self.path + '/train'
        train_image_files, val_image_files = training_validation_data_split(data_path)

        steps_per_epoch = int(len(train_image_files)/self.batchsize)

        self.epochs = self.iterations_over_dataset
        logging.info("Making: %s steps per Epoch" % steps_per_epoch)
        return [Training_Input_shape, num_channels, network_input_size, Input_image_shape,
                        data_path, train_image_files, val_image_files, steps_per_epoch, data_dimensions,val_image_files]



    def data_generator(self, data_path, Training_Input_shape, num_channels, train_image_files, data_dimensions, val_image_files):
        '''
        Prepare data as a Training and Validation set
        Args:
            data_path: Path to folder containing the dataset
            Training_Input_shape: Shape of the input images in the train folder
            num_channels: Number of channels (e.g.: 3 for RGB)
            train_image_files: List of filenames contained in the train set
            val_image_files: List of filenames contained in the validation set
            data_dimensions: Image dimensions
        return:
            Two data generators (train & validation) and the number of channels of the groundtruth (label)
        '''

        img_file_label_name = os.listdir(data_path + "/groundtruth/")[0]
        logging.info("img_file_label_name: %s" % img_file_label_name)
        Training_Input_shape_label = np.shape(np.array(import_image(data_path + "/groundtruth/" + img_file_label_name)))
        num_channels_label = Training_Input_shape_label[-1]
        if all([num_channels_label != 1, num_channels_label != 3]):
            num_channels_label = 1

        if self.use_algorithm == "SemanticSegmentation":
            self.data_gen_args["binarize_mask"] = True

        TrainingDataGenerator = training_data_generator(Training_Input_shape,
                                                            self.batchsize, num_channels,
                                                            num_channels_label,
                                                            train_image_files,
                                                            self.data_gen_args,
                                                            data_dimensions,
                                                            data_path,
                                                            self.use_algorithm)
        ValidationDataGenerator = training_data_generator(Training_Input_shape,
                                                              self.batchsize, num_channels,
                                                              num_channels_label,
                                                              val_image_files,
                                                              self.data_gen_args,
                                                              data_dimensions,
                                                              data_path,
                                                              self.use_algorithm)
        return TrainingDataGenerator, ValidationDataGenerator,num_channels_label
    
    def load_model(self, network_input_size,data_dimensions,num_channels_label ):
        '''
        Build a 2D or 3D U-Net model and initialize it with pretrained or random weights
        Args:
            network_input_size: Dimensions of one input image (e.g. 128,128,3)
            data_dimensions: Dimensions of the data (e.g. 3)
            num_channels_label: Number of channels of the groundtruth
        returns:
            A 2D or 3D UNet model
        '''
        if self.pretrained_weights == False:
            self.pretrained_weights = None
        if data_dimensions == 3:
            logging.info("Using 3D UNet")
            model = UNetBuilder.unet3D(self.pretrained_weights, network_input_size[-1], num_channels_label, self.num_classes, self.loss_function, Dropout_On = True)
        else:
            logging.info("Using 2D UNet")
            model = UNetBuilder.unet2D(self.pretrained_weights, network_input_size[-1], num_channels_label, self.num_classes, self.loss_function, Dropout_On = True)

        logging.info(model.summary())
        return model

    def train_model(self, model,TrainingDataGenerator,ValidationDataGenerator , steps_per_epoch, val_image_files ):
        '''
        Set Model callbacks such as: 
        - Early stopping (after the validation loss has not improved for 25 epochs
        - Checkpoints: Save model after each epoch if the validation loss has improved 
        - Tensorboard: Monitor training live with tensorboard. Start tensorboard in terminal with: tensorboard --logdir=/path_to/logs 
        Args:
            model: The initialized U-Net model
            TrainingDataGenerator: The train data generator
            ValidationDataGenerator: The validation data generator
            steps_per_epoch: The number of train steps in one epoch
            val_image_files: List of validation files
        returns:
            The trained model and the checkpoint file path
        '''
        early_stopping = EarlyStopping(monitor='val_loss', patience=5, mode='auto', verbose=0)
        datasetname = self.path.rsplit("/",1)[1]
        checkpoint_filepath = (self.path + "/logs" + "/pretrained_weights" + datasetname + ".hdf5") #.{epoch:02d}.hdf5")
        os.makedirs((self.path + "/logs"), exist_ok=True)
        model_checkpoint = ModelCheckpoint(checkpoint_filepath, monitor=('val_loss'), verbose=1, save_best_only=True)

        tensorboard = TensorBoard(log_dir=self.path + "logs/" + "/" + format(time.time()))  # , update_freq='batch')
        logging.info("Tensorboard log is created at: logs/  it can be opend using tensorboard --logdir=logs for a terminal in the Project folder")
        callbacks_list = [model_checkpoint, tensorboard, early_stopping]

        '''
        Train the model given the initialized model and the data from the data generator
        '''
        assert self.num_classes == 1
        model.fit_generator(TrainingDataGenerator,
                                steps_per_epoch=steps_per_epoch,
                                validation_data=ValidationDataGenerator,
                                validation_steps=int(len(val_image_files)/self.batchsize),
                                max_queue_size=50,
                                epochs=self.epochs,
                                callbacks = callbacks_list,
                                use_multiprocessing=True)
        logging.info('finished Model.fit_generator')
        return model, checkpoint_filepath

    def test_set_evaluation(self, model, Training_Input_shape, num_channels,Input_image_shape):
        '''
        Evalute the model on the testset
        Args:
            model: the trained or initialized model
            Training_Input_shape: The dimensions of the input data
            num_channels: the number of channels
            Input_image_shape: The shape of the input images
        returns: the results of the tested images, a list of filenames of the testset, the number of images tested
        '''

        test_image_files = os.listdir(os.path.join(self.path + "/test/image"))
        num_test_img = int(len(os.listdir(self.path + "/test/image")))
        #logging.info("Testing on", num_test_img, "test files")

        '''
        Initialize the testset generator
        '''
        testGene = testGenerator(Training_Input_shape, self.path, num_channels, test_image_files, self.use_algorithm)
        logging.info('finished testGene')
        results = model.predict_generator(testGene, steps=num_test_img, use_multiprocessing=False, verbose=1)
        #logging.info("results"), np.shape(results))
        logging.info('finished model.predict_generator')


        '''
        Save the models prediction on the testset by printing the predictions 
        as images to the results folder in the project path
        '''
        saveResult(self.path + "/results/", test_image_files, results, Input_image_shape)
        if self.calculate_uncertainty == False:
            if self.evaluation == True:
                segmentation_regression_evaluation(self.path)

        return results,test_image_files, num_test_img
        ################################################# if calculate_uncertainty == True:
    def uncertainty_prediction(self, results, 
                                checkpoint_filepath, 
                                network_input_size, 
                                Training_Input_shape, 
                                num_channels, 
                                test_image_files, 
                                num_test_img,
                                data_dimensions ,  
                                num_channels_label, 
                                Input_image_shape):    


        '''
        Start uncertainty prediction if selected for regression or semantic segmentation
        As suggested by Gal et. al.: https://arxiv.org/abs/1506.02142 
        And as implemented in: https://openreview.net/pdf?id=Sk_P2Q9sG
        Args:
            checkpoint_filepath: the directory where checkpoints are saved
            network_input_size: the dimensions of the input to the network
            Training_Input_shape: the shape of the images in the train dataset
            num_channels: number of channels (e.g.: 3 for RGB)
            test_image_files: list of filenames contained in the testset
            num_test_img: number of filenames in the testset
            data_dimensions: image dimensions
            num_channels_label: number of channels of the groundtruth (e.g.: 3 for RGB)
            Input_image_shape: The shape of the input images
        returns:
            Saves the results to the 'results' directory and the uncertainty estimations to the 'uncertainty' directory
        '''
        if data_dimensions == 3:
            logging.info("Using 3D UNet")
            if self.epochs > 0:
                uncertainty_weights = checkpoint_filepath
            else:
                uncertainty_weights = self.pretrained_weights
            model = UNetBuilder.unet3D(uncertainty_weights,
                                               network_input_size[-1],
                                               num_channels_label,
                                               loss_function = self.loss_function,
                                               num_classes = self.num_classes,
                                               Dropout_On=True)
        else:
            logging.info("Using 2D UNet")
            if self.epochs > 0:
                uncertainty_weights = checkpoint_filepath
            else:
                uncertainty_weights = self.pretrained_weights
            model = UNetBuilder.unet2D(uncertainty_weights,
                                               network_input_size[-1],
                                               num_channels_label,
                                               loss_function = self.loss_function,
                                               num_classes = self.num_classes,
                                               Dropout_On = True)
        resultsMCD = []
        for i in range(0, 20):
            testGene = testGenerator(Training_Input_shape, self.path, num_channels, test_image_files, self.use_algorithm)
            resultsMCD.append(model.predict_generator(testGene,
                                                              steps=num_test_img,
                                                              use_multiprocessing=False,
                                                              verbose=1))
        resultsMCD = np.array(resultsMCD)
        # Implementation following: https://github.com/ykwon0407/UQ_BNN
        aleatoric_uncertainty = np.mean(resultsMCD * (1 - resultsMCD), axis=0)
        epistemic_uncertainty = np.mean(resultsMCD**2, axis = 0) - np.mean(resultsMCD, axis = 0)**2
        saveUncertainty(self.path + "/insights/", test_image_files, epistemic_uncertainty, aleatoric_uncertainty)
        uncertainty = epistemic_uncertainty + aleatoric_uncertainty
        saveResult(self.path + "/uncertainty/", test_image_files, uncertainty, Input_image_shape)
        if self.evaluation == True:
            segmentation_regression_evaluation(self.path)

    def run(self):    
        data_prepration_results = self.data_prepration()
        
        Training_Input_shape = data_prepration_results[0]
        num_channels = data_prepration_results[1]
        network_input_size = data_prepration_results[2]
        Input_image_shape = data_prepration_results[3]
        data_path = data_prepration_results[4]
        train_image_files = data_prepration_results[5]
        val_image_files = data_prepration_results[6] 
        steps_per_epoch = data_prepration_results[7]
        data_dimensions = data_prepration_results[8]
        val_image_files = data_prepration_results[9]

        TrainingDataGenerator, ValidationDataGenerator, num_channels_label = self.data_generator(   data_path, 
                                                                            Training_Input_shape, 
                                                                            num_channels, 
                                                                            train_image_files, 
                                                                            data_dimensions, 
                                                                            val_image_files)

        model = self.load_model( network_input_size,data_dimensions,num_channels_label)

        model, checkpoint_filepath = self.train_model(  model,
                                                        TrainingDataGenerator,
                                                        ValidationDataGenerator , 
                                                        steps_per_epoch, 
                                                        val_image_files  )

        results,test_image_files, num_test_img = self.test_set_evaluation( model, 
                                                                        Training_Input_shape, 
                                                                        num_channels,
                                                                        Input_image_shape)

        if self.calculate_uncertainty == True:
            self.uncertainty_prediction(    results,
                                            checkpoint_filepath,
                                            network_input_size,
                                            Training_Input_shape,
                                            num_channels,
                                            test_image_files,
                                            num_test_img,
                                            data_dimensions ,
                                            num_channels_label,
                                            Input_image_shape)
        model = None
    
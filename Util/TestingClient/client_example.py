#!/usr/bin/env python3

# Copyright (c) 2017 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB), and the INTEL Visual Computing Lab.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""Basic CARLA client example."""


import argparse
import logging
import random
import shutil
import sys
import time


from carla.client import make_carla_client
from carla.console import CarlaClientConsole
from carla.settings import CarlaSettings, Camera


def run_carla_client(host, port, autopilot_on, save_images_to_disk, image_filename_format):
    # Here we will run 3 episodes with 300 frames each.
    number_of_episodes = 3
    frames_per_episode = 300

    # We assume the CARLA server is already waiting for a client to connect at
    # host:port. To create a connection we can use the `make_carla_client`
    # context manager, it creates a CARLA client object and starts the
    # connection. It will throw an exception if something goes wrong. The
    # context manager makes sure the connection is always cleaned up on exit.
    with make_carla_client(host, port) as client:
        print('CarlaClient connected')

        for episode in range(0, number_of_episodes):
            # Start a new episode.

            # Create a CarlaSettings object. This object is a handy wrapper
            # around the CarlaSettings.ini file. Here we set the configuration
            # we want for the new episode.
            settings = CarlaSettings()
            settings.set(
                SynchronousMode=True,
                NumberOfVehicles=30,
                NumberOfPedestrians=50,
                WeatherId=random.choice([1, 3, 7, 8, 14]))
            settings.randomize_seeds()

            # Now we want to add a couple of cameras to the player vehicle. We
            # will collect the images produced by these cameras every frame.

            # The default camera captures RGB images of the scene.
            camera0 = Camera('CameraRGB')
            # Set image resolution in pixels.
            camera0.set_image_size(800, 600)
            # Set its position relative to the car in centimeters.
            camera0.set_position(30, 0, 130)
            settings.add_camera(camera0)

            # Let's add another camera producing ground-truth depth.
            camera1 = Camera('CameraDepth', PostProcessing='Depth')
            camera1.set_image_size(800, 600)
            camera1.set_position(30, 0, 130)
            settings.add_camera(camera1)

            print('Requesting new episode...')

            # Now we request a new episode with these settings. The server
            # replies with a scene description containing the available start
            # spots for the player. Here instead of a CarlaSettings object we
            # could also provide a CarlaSettings.ini file as string.
            scene = client.request_new_episode(settings)

            # Choose one player start at random.
            number_of_player_starts = len(scene.player_start_spots)
            player_start = random.randint(0, max(0, number_of_player_starts - 1))

            # Notify the server that we want to start the episode at
            # `player_start`. This function blocks until the server is ready to
            # start the episode.
            client.start_episode(player_start)

            # Iterate every frame in the episode.
            for frame in range(0, frames_per_episode):

                # Read the measurements and images produced by the server this
                # frame.
                measurements, images = client.read_measurements()

                # Print some of the measurements we received.
                print_player_measurements(measurements.player_measurements)

                # Save the images to disk if requested.
                if save_images_to_disk:
                    for n, image in enumerate(images):
                        image.save_to_disk(image_filename_format.format(episode, n, frame))

                # Now we have to send the instructions to control the vehicle.
                # If we are in synchronous mode the server will pause the
                # simulation until we send this control.

                if not autopilot_on:

                    client.send_control(
                        steer=random.uniform(-1.0, 1.0),
                        throttle=0.3,
                        brake=False,
                        hand_brake=False,
                        reverse=False)

                else:

                    # Together with the measurements, the server has sent the
                    # control that the in-game AI would do this frame. We can
                    # enable autopilot by sending back this control to the
                    # server. Here we will also add some noise to the steer.

                    control = measurements.player_measurements.ai_control
                    control.steer += random.uniform(-0.1, 0.1)
                    client.send_control(control)

    print('Done.')
    return True


def print_player_measurements(player_measurements):
    message = 'Vehicle at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f}) '
    message += '{speed:.2f} km/h, '
    message += '{other_lane:.0f}% other lane, {offroad:.0f}% off-road'
    message = message.format(
        pos_x=player_measurements.transform.location.x / 100, # cm -> m
        pos_y=player_measurements.transform.location.y / 100,
        pos_z=player_measurements.transform.location.z / 100,
        speed=player_measurements.forward_speed,
        other_lane=100 * player_measurements.intersection_otherlane,
        offroad=100 * player_measurements.intersection_offroad)
    empty_space = shutil.get_terminal_size((80, 20)).columns - len(message)
    sys.stdout.write('\r' + message + empty_space * ' ')
    sys.stdout.flush()


def main():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        help='print debug information')
    argparser.add_argument(
        '--host',
        metavar='H',
        default='127.0.0.1',
        help='IP of the host server (default: 127.0.0.1)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port to listen to (default: 2000)')
    argparser.add_argument(
        '-a', '--autopilot',
        action='store_true',
        help='enable autopilot')
    argparser.add_argument(
        '-i', '--images-to-disk',
        action='store_true',
        help='save images to disk')
    argparser.add_argument(
        '-c', '--console',
        action='store_true',
        help='start the client console')

    args = argparser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format='carla_client: %(levelname)s: %(message)s', level=log_level)

    logging.info('listening to server %s:%s', args.host, args.port)

    if args.console:
        args.synchronous = True
        cmd = CarlaClientConsole(args)
        try:
            cmd.cmdloop()
        finally:
            cmd.cleanup()
        return

    while True:
        try:

            end = run_carla_client(
                host=args.host,
                port=args.port,
                autopilot_on=args.autopilot,
                save_images_to_disk=args.images_to_disk,
                image_filename_format='_images/episode_{:0>3d}/camera_{:0>3d}/image_{:0>5d}.png')

            if end:
                return

        except Exception as exception:
            logging.error('exception: %s', exception)
            time.sleep(1)


if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')
